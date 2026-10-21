package dispatcher_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strconv"
	"testing"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/controlclient"
	"pwnmesh/internal/protocol"
)

func TestExecutionLeaseWireContract(t *testing.T) {
	lease := controlclient.Lease{Run: "worker@run", Kind: "explore", Intent: "step"}
	step := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		var body map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		paths := []string{"/projects/project/intents/step/heartbeat", "/projects/project/intents/step/heartbeat", "/projects/project/executions/run/status", "/projects/project/executions/run/apply", "/projects/project/intents/step/release"}
		if step >= len(paths) {
			t.Error("unexpected extra request")
			w.WriteHeader(500)
			return
		}
		if r.Method != "POST" || r.URL.Path != paths[step] {
			t.Errorf("request %d: %s %s", step, r.Method, r.URL.Path)
		}
		fenced := step == 1 || step == 2 || step == 3
		if fenced && (r.Header.Get("X-PwnMesh-Run") != lease.Run || r.Header.Get("X-PwnMesh-Lease") != lease.Kind || r.Header.Get("X-PwnMesh-Intent") != lease.Intent) {
			t.Error("missing execution fence")
		}
		if !fenced && r.Header.Get("X-PwnMesh-Run") != "" {
			t.Error("management operation received execution authority")
		}
		switch step {
		case 0, 4:
			if !reflect.DeepEqual(body, map[string]json.RawMessage{"worker": json.RawMessage(`"worker@run"`)}) {
				t.Errorf("lease body: %s", body)
			}
		case 1:
			if string(body["worker"]) != `"worker@run"` || string(body["expected_version"]) != `"snapshot"` || len(body) != 2 {
				t.Errorf("renew body: %s", body)
			}
		case 2:
			var result protocol.Result
			if err := json.Unmarshal(body["result"], &result); err != nil || result.Status != "success" || string(body["status"]) != `"result_pending"` {
				t.Errorf("status body: %s", body)
			}
		case 3:
			if len(body) != 0 {
				t.Errorf("apply must not carry a second result: %s", body)
			}
		}
		step++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"succeeded"}`))
	}))
	defer server.Close()
	client := &controlclient.Client{Base: server.URL}
	ctx := context.Background()
	if err := client.Claim(ctx, "project", lease, ""); err != nil {
		t.Fatal(err)
	}
	if err := client.Renew(ctx, "project", lease, "snapshot"); err != nil {
		t.Fatal(err)
	}
	if err := client.ChangeStatus(ctx, "project", "run", "result_pending", protocol.Result{Status: "success"}, lease); err != nil {
		t.Fatal(err)
	}
	if status, err := client.Apply(ctx, "project", "run", lease); err != nil || status != "succeeded" {
		t.Fatalf("apply = %q, %v", status, err)
	}
	if err := client.Release(ctx, "project", lease); err != nil {
		t.Fatal(err)
	}
	if step != 5 {
		t.Fatalf("requests = %d", step)
	}
}

func TestScheduleSnapshotAndStructuredFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/projects/project/scheduling" {
			q := r.URL.Query()
			if q.Get("namespace") != "ns" || q.Get("offset") != "12" || q.Get("expected_version") != "stable" || q.Get("protocol_version") != strconv.Itoa(board.ScheduleProtocolVersion) {
				t.Errorf("scheduling query = %v", q)
			}
			_ = json.NewEncoder(w).Encode(board.SchedulePage{ProtocolVersion: board.ScheduleProtocolVersion, StateVersion: "stable"})
			return
		}
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"code":"state_changed","error":"snapshot changed"}`))
	}))
	defer server.Close()
	client := &controlclient.Client{Base: server.URL}
	page, err := client.Schedule(context.Background(), "project", controlclient.ScheduleQuery{Namespace: "ns", Offset: 12, ExpectedVersion: "stable"})
	if err != nil || page.StateVersion != "stable" {
		t.Fatalf("schedule = %+v, %v", page, err)
	}
	err = client.Renew(context.Background(), "project", controlclient.Lease{Kind: "reason", Run: "worker@run"}, "stable")
	var failure *protocol.RPCError
	if !errors.As(err, &failure) || failure.Code != board.CodeStateChanged || failure.Status != 409 {
		t.Fatalf("lost structured failure: %v", err)
	}
}

func TestScheduleRejectsIncompatibleProtocol(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(board.SchedulePage{ProtocolVersion: board.ScheduleProtocolVersion + 1})
	}))
	defer server.Close()
	client := &controlclient.Client{Base: server.URL}
	if _, err := client.Schedule(context.Background(), "project", controlclient.ScheduleQuery{}); err == nil {
		t.Fatal("incompatible schedule was accepted")
	}
}
