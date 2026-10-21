// Package launchbridge binds Worker RPCs to one launch independently of its transport.
package launchbridge

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"time"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/modelrpc"
	"pwnmesh/internal/modelwire"
	"pwnmesh/internal/protocol"
)

// Each bridge is bound to one launch. Only the dispatcher sees the upstream
// endpoint and credentials; worker messages cannot choose either of them.
const MaxModelConcurrency = 16

type Model struct {
	ctx       context.Context
	cancel    context.CancelFunc
	job       protocol.Job
	options   ModelOptions
	deliver   func(context.Context, modelrpc.Response) error
	fail      func(error)
	mu        sync.Mutex
	active    map[string]context.CancelFunc
	seen      map[string]bool
	wg        sync.WaitGroup
	slots     chan struct{}
	admission chan struct{}
}

// ModelSession keeps provider transport and credential lookup outside the bridge.
type ModelSession interface {
	agent.Provider
	CredentialValues() []string
}

// ModelOptions fixes authority and upstream policy for the lifetime of one launch.
// NewSession returns an independent client for the validated run or child identity.
type ModelOptions struct {
	Job        protocol.Job
	MaxTokens  int
	Timeout    time.Duration
	NewSession func(string) ModelSession
	Deliver    func(context.Context, modelrpc.Response) error
	Fail       func(error)
	Admission  chan struct{}
}

func NewModel(parent context.Context, options ModelOptions) *Model {
	ctx, cancel := context.WithCancel(parent)
	return &Model{ctx: ctx, cancel: cancel, options: options, job: options.Job,
		deliver: options.Deliver, fail: options.Fail, admission: options.Admission,
		active: map[string]context.CancelFunc{}, seen: map[string]bool{}, slots: make(chan struct{}, 32)}
}

func (b *Model) Close() {
	// Pair cancellation with start's context check and WaitGroup.Add. Once the
	// lock is released no new call can be admitted while Wait observes zero.
	b.mu.Lock()
	b.cancel()
	b.mu.Unlock()
	b.wg.Wait()
}

func (b *Model) Stop(id string) error {
	if !protocol.ValidGraphRequestID(id) {
		return errors.New("invalid model cancellation ID")
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if cancel := b.active[id]; cancel != nil {
		cancel()
	}
	return nil
}

func (b *Model) Start(r modelrpc.Request) error {
	if b.options.NewSession == nil || b.deliver == nil || b.fail == nil {
		return errors.New("model bridge is not configured")
	}
	if !protocol.ValidGraphRequestID(r.RequestID) {
		return errors.New("invalid model request ID")
	}
	if r.SessionID != b.job.RunID {
		parts := strings.Split(r.SessionID, ":")
		if len(parts) != 3 || parts[0] != b.job.RunID || b.job.Kind != "explore" || !modelSessionPart(parts[1]) || !modelSessionPart(parts[2]) {
			return errors.New("model session does not belong to this run")
		}
	}
	if r.SummaryTokens < 0 || r.SummaryTokens > b.options.MaxTokens {
		return errors.New("invalid model summary allowance")
	}
	if r.SummaryTokens > 0 && len(r.Tools) > 0 {
		return errors.New("summary requests cannot declare tools")
	}
	raw, err := json.Marshal(r)
	if err != nil || len(raw) > modelrpc.MaxRequestBytes {
		return errors.New("model request exceeds its byte limit")
	}
	// A published response can trigger another turn before its delivery has
	// finished. Bound those overlapping deliveries with cancelable backpressure,
	// without holding the lock that delivery completion and close require.
	select {
	case b.slots <- struct{}{}:
	case <-b.ctx.Done():
		return b.ctx.Err()
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.ctx.Err() != nil {
		<-b.slots
		return b.ctx.Err()
	}
	if b.seen[r.RequestID] || len(b.seen) >= 4096 || len(b.active) >= MaxModelConcurrency {
		<-b.slots
		return errors.New("model bridge request limit or duplicate ID")
	}
	ctx, cancel := context.WithTimeout(b.ctx, b.options.Timeout)
	if !r.Deadline.IsZero() {
		var shorten context.CancelFunc
		ctx, shorten = context.WithDeadline(ctx, r.Deadline)
		original := cancel
		cancel = func() { shorten(); original() }
	}
	b.seen[r.RequestID], b.active[r.RequestID] = true, cancel
	b.wg.Add(1)
	go func() {
		defer b.wg.Done()
		defer cancel()
		defer func() { <-b.slots }()
		response := b.generateAdmitted(ctx, r)
		// Free the model slot before publishing its response. The worker can
		// issue its next turn as soon as delivery publishes, before delivery returns.
		b.mu.Lock()
		delete(b.active, r.RequestID)
		b.mu.Unlock()
		// A canceled individual call still needs a typed reply; the enclosing
		// launch owns delivery. Finishing a launch cancels every outstanding call.
		if b.ctx.Err() == nil {
			delivery, stopDelivery := context.WithTimeout(b.ctx, modelrpc.DeliveryTimeout)
			defer stopDelivery()
			if err := b.deliver(delivery, response); err != nil {
				b.fail(errors.New("model bridge response delivery failed"))
			}
		}
	}()
	return nil
}

// Wait inside the request goroutine so model cancellation and graph frames can
// still be consumed. Delivery has its own bound and never holds provider capacity.
func (b *Model) generateAdmitted(ctx context.Context, r modelrpc.Request) (response modelrpc.Response) {
	queued := time.Now()
	timing := agent.ModelTiming{Calls: 1}
	defer func() { response.Message.Timing = &timing }()
	if b.admission != nil {
		select {
		case b.admission <- struct{}{}:
			defer func() { <-b.admission }()
		case <-ctx.Done():
			timing.QueueMS = time.Since(queued).Milliseconds()
			return modelrpc.Response{RequestID: r.RequestID, Error: safeModelError(ctx.Err())}
		}
	}
	timing.QueueMS = time.Since(queued).Milliseconds()
	if err := ctx.Err(); err != nil {
		return modelrpc.Response{RequestID: r.RequestID, Error: safeModelError(err)}
	}
	started := time.Now()
	timing.ProviderCalls = 1
	response = b.generate(ctx, r)
	timing.ProviderMS = time.Since(started).Milliseconds()
	return response
}

func modelSessionPart(s string) bool {
	if len(s) == 0 || len(s) > 128 {
		return false
	}
	for _, ch := range s {
		if !(ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' || ch == '-' || ch == '_') {
			return false
		}
	}
	return true
}

func safeModelError(err error) *modelrpc.Error {
	if err == nil {
		return nil
	}
	out := &modelrpc.Error{Kind: agent.ErrorProvider, Canceled: errors.Is(err, context.Canceled), Deadline: errors.Is(err, context.DeadlineExceeded)}
	var model *agent.ModelError
	if errors.As(err, &model) {
		switch model.Kind {
		case agent.ErrorContextOverflow, agent.ErrorTransport, agent.ErrorRateLimit, agent.ErrorUnavailable, agent.ErrorProvider, agent.ErrorToolArguments, agent.ErrorBudget:
			out.Kind = model.Kind
		}
	} else if out.Canceled || out.Deadline {
		out.Kind = ""
	}
	var endpoint *modelwire.HTTPError
	if errors.As(err, &endpoint) && endpoint.Status >= 100 && endpoint.Status <= 599 {
		out.HTTPStatus = endpoint.Status
	}
	return out
}

func (b *Model) generate(ctx context.Context, r modelrpc.Request) modelrpc.Response {
	// A fresh provider keeps simultaneous child sessions independent. Their
	// identity comes from this run, and all upstream policy remains fixed.
	p := b.options.NewSession(r.SessionID)
	out := modelrpc.Response{RequestID: r.RequestID}
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	var eventBytes int
	tooLarge := false
	emit := func(e agent.Event) {
		raw, err := json.Marshal(e)
		eventBytes += len(raw)
		if err != nil || eventBytes > 32<<20 {
			tooLarge = true
			cancel()
			return
		}
		out.Events = append(out.Events, e)
	}
	var err error
	if r.SummaryTokens > 0 {
		out.Message, err = p.GenerateSummary(ctx, r.Messages, r.SummaryTokens, emit)
	} else {
		out.Message, err = p.Generate(ctx, r.Messages, r.Tools, emit)
	}
	out.Error = safeModelError(err)
	raw, marshalErr := json.Marshal(out)
	// Delay delta publication until the complete response can be checked. A
	// malicious upstream could echo an authentication token split across deltas.
	var text strings.Builder
	for _, e := range out.Events {
		text.WriteString(e.Text)
	}
	if tooLarge || marshalErr != nil || len(raw) > modelrpc.MaxResponseBytes || JSONContainsCredential(raw, p.CredentialValues()...) || ContainsCredential(text.String(), p.CredentialValues()...) {
		// Numeric usage is independent of rejected content and remains an observation
		// even when the response cannot cross the credential/size boundary.
		return modelrpc.Response{RequestID: r.RequestID, Message: agent.Message{Usage: out.Message.Usage}, Error: &modelrpc.Error{Kind: agent.ErrorProvider}}
	}
	return out
}
