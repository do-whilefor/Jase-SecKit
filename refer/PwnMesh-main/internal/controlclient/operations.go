package controlclient

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"

	board "pwnmesh/internal/board/model"
	"pwnmesh/internal/protocol"
)

var _ Server = (*Client)(nil)

func executionPath(project, run string) string {
	return projectPath(project) + "/executions/" + url.PathEscape(run)
}

func leasePath(project string, lease Lease) string {
	base := projectPath(project)
	if lease.Kind == "reason" || lease.Kind == "curate" {
		return base + "/" + lease.Kind
	}
	return base + "/intents/" + url.PathEscape(lease.Intent)
}

func (c *Client) Installation(ctx context.Context) (string, error) {
	var deployment struct {
		ID string `json:"installation_id"`
	}
	err := c.do(ctx, "GET", "/deployment", nil, &deployment, nil)
	return deployment.ID, err
}

func (c *Client) DispatcherLease(ctx context.Context, namespace, holder, installation, op string) error {
	if op != "claim" && op != "heartbeat" && op != "release" {
		return fmt.Errorf("invalid dispatcher lease operation %q", op)
	}
	body := struct {
		Holder       string `json:"holder"`
		Installation string `json:"installation_id"`
	}{holder, installation}
	return c.do(ctx, "POST", "/dispatchers/"+url.PathEscape(namespace)+"/"+op, body, nil, nil)
}

func (c *Client) Settings(ctx context.Context) (board.Settings, error) {
	var settings board.Settings
	err := c.do(ctx, "GET", "/settings", nil, &settings, nil)
	return settings, err
}

func (c *Client) Schedule(ctx context.Context, project string, input ScheduleQuery) (board.SchedulePage, error) {
	query := url.Values{"protocol_version": {strconv.Itoa(board.ScheduleProtocolVersion)}}
	if input.Namespace != "" {
		query.Set("namespace", input.Namespace)
	}
	if input.Offset != 0 {
		query.Set("offset", strconv.Itoa(input.Offset))
	}
	if input.ExpectedVersion != "" {
		query.Set("expected_version", input.ExpectedVersion)
	}
	var page board.SchedulePage
	if err := c.do(ctx, "GET", projectPath(project)+"/scheduling?"+query.Encode(), nil, &page, nil); err != nil {
		return board.SchedulePage{}, err
	}
	if page.ProtocolVersion != board.ScheduleProtocolVersion {
		return board.SchedulePage{}, fmt.Errorf("scheduling protocol mismatch: Server returned version %d, Dispatcher requires %d; upgrade Server and Dispatcher together", page.ProtocolVersion, board.ScheduleProtocolVersion)
	}
	return page, nil
}

func (c *Client) PendingExecutions(ctx context.Context, namespace string, after int64) (board.ExecutionPage, error) {
	query := url.Values{"namespace": {namespace}, "after": {strconv.FormatInt(after, 10)}, "limit": {"100"}}
	var page board.ExecutionPage
	err := c.do(ctx, "GET", "/executions/pending?"+query.Encode(), nil, &page, nil)
	return page, err
}

func (c *Client) Prepare(ctx context.Context, execution board.Execution, lease Lease) (board.Execution, error) {
	var saved board.Execution
	err := c.do(ctx, "POST", projectPath(execution.ProjectID)+"/executions/prepare", execution, &saved, &lease)
	return saved, err
}

func (c *Client) Execution(ctx context.Context, project, run, namespace string) (board.Execution, error) {
	var execution board.Execution
	err := c.do(ctx, "GET", executionPath(project, run)+"?namespace="+url.QueryEscape(namespace), nil, &execution, nil)
	return execution, err
}

func (c *Client) Resume(ctx context.Context, project, run string, lease Lease) (board.Execution, error) {
	var execution board.Execution
	err := c.do(ctx, "POST", executionPath(project, run)+"/resume", struct{}{}, &execution, &lease)
	return execution, err
}

func (c *Client) ChangeStatus(ctx context.Context, project, run, status string, result protocol.Result, lease Lease) error {
	body := struct {
		Status string          `json:"status"`
		Result protocol.Result `json:"result"`
	}{status, result}
	return c.do(ctx, "POST", executionPath(project, run)+"/status", body, nil, &lease)
}

func (c *Client) Apply(ctx context.Context, project, run string, lease Lease) (string, error) {
	var receipt struct {
		Status string `json:"status"`
	}
	err := c.do(ctx, "POST", executionPath(project, run)+"/apply", struct{}{}, &receipt, &lease)
	return receipt.Status, err
}

func (c *Client) Retry(ctx context.Context, project, run string, automatic bool) error {
	return c.do(ctx, "POST", executionPath(project, run)+"/retry", struct {
		Automatic bool `json:"automatic"`
	}{automatic}, nil, nil)
}

func (c *Client) Observe(ctx context.Context, project, run string, metrics *protocol.DecisionMetrics, lease Lease) error {
	return c.do(ctx, "POST", executionPath(project, run)+"/observation", struct {
		Metrics *protocol.DecisionMetrics `json:"metrics"`
	}{metrics}, nil, &lease)
}

func (c *Client) Claim(ctx context.Context, project string, lease Lease, trigger string) error {
	path := leasePath(project, lease)
	var body any = struct {
		Worker string `json:"worker"`
	}{lease.Run}
	if lease.Kind == "reason" || lease.Kind == "curate" {
		path += "/claim"
		body = struct {
			Worker  string `json:"worker"`
			Trigger string `json:"trigger"`
		}{lease.Run, trigger}
	} else {
		path += "/heartbeat"
	}
	return c.do(ctx, "POST", path, body, nil, nil)
}

func (c *Client) Renew(ctx context.Context, project string, lease Lease, version string) error {
	body := struct {
		Worker  string `json:"worker"`
		Version string `json:"expected_version,omitempty"`
	}{lease.Run, version}
	return c.do(ctx, "POST", leasePath(project, lease)+"/heartbeat", body, nil, &lease)
}

func (c *Client) Release(ctx context.Context, project string, lease Lease) error {
	return c.do(ctx, "POST", leasePath(project, lease)+"/release", struct {
		Worker string `json:"worker"`
	}{lease.Run}, nil, nil)
}

func (c *Client) ExecutionIdentity(ctx context.Context, project, run, namespace string) (board.ExecutionSummary, error) {
	var identity board.ExecutionSummary
	err := c.do(ctx, "GET", executionPath(project, run)+"/identity?namespace="+url.QueryEscape(namespace), nil, &identity, nil)
	return identity, err
}

func (c *Client) CurationReceipt(ctx context.Context, project string, lease Lease) (CurationReceipt, error) {
	var receipt CurationReceipt
	err := c.do(ctx, "GET", projectPath(project)+"/state/curation/receipt", nil, &receipt, &lease)
	return receipt, err
}

func (c *Client) Decision(ctx context.Context, project, op string, batch *board.DecisionBatch, lease Lease) (board.DecisionReceipt, error) {
	method := "POST"
	var body any = batch
	if op == "receipt" {
		method, body = "GET", nil
	} else if op != "preview" && op != "commit" {
		return board.DecisionReceipt{}, fmt.Errorf("unknown decision operation %q", op)
	}
	var receipt board.DecisionReceipt
	err := c.do(ctx, method, projectPath(project)+"/state/decisions/"+op, body, &receipt, &lease)
	return receipt, err
}

func (c *Client) ReadGraph(ctx context.Context, project, run string, request protocol.GraphRequest, lease Lease) (json.RawMessage, error) {
	var path string
	switch request.Op {
	case "read_graph":
		path = projectPath(project) + "/state/read"
	case "read_snapshot":
		path = executionPath(project, run) + "/input/read"
	case "read_updates":
		path = executionPath(project, run) + "/updates"
	case "read_trace_runs":
		path = executionPath(project, run) + "/traces/read"
	default:
		return nil, fmt.Errorf("unknown graph read operation %q", request.Op)
	}
	var page json.RawMessage
	err := c.do(ctx, "POST", path, request, &page, &lease)
	return page, err
}

func (c *Client) GraphAction(ctx context.Context, project string, action board.StateAction, lease Lease) (board.StateActionResult, error) {
	var result board.StateActionResult
	err := c.do(ctx, "POST", projectPath(project)+"/state/actions", action, &result, &lease)
	return result, err
}
