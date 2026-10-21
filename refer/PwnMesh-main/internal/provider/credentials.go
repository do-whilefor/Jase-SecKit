package provider

import (
	"context"
	"errors"
	"sync"

	"pwnmesh/internal/agent"
	"pwnmesh/internal/kimi"
	"pwnmesh/internal/modelauth"
	"pwnmesh/internal/modelwire"
)

func (p *Client) configureCredentialSource(ctx context.Context, id string, source CredentialSource) error {
	if !modelauth.ValidCredentialID(id) {
		return errors.New("invalid subscription credential reference")
	}
	var mu sync.Mutex
	var secrets []string
	p.TokenSource = func(ctx context.Context) (string, error) {
		token, err := source(ctx, id)
		if err != nil {
			return "", classifyCredentialError(err)
		}
		mu.Lock()
		found := false
		for _, known := range secrets {
			found = found || known == token
		}
		if !found && token != "" {
			secrets = append(secrets, token)
		}
		mu.Unlock()
		return token, nil
	}
	p.Secrets = func() []string { mu.Lock(); defer mu.Unlock(); return append([]string(nil), secrets...) }
	token, err := p.TokenSource(ctx)
	if err != nil {
		return err
	}
	p.Token = token
	return nil
}

func (p *Client) configureKimi(ctx context.Context, dir, id string) error {
	store := &kimi.Store{Dir: dir, Client: &kimi.Client{HTTP: p.Client}}
	initial, err := store.Read(ctx, id)
	if err != nil {
		return err
	}
	p.Token = initial.AccessToken
	var mu sync.Mutex
	secrets := []string{initial.AccessToken, initial.RefreshToken}
	p.TokenSource = func(ctx context.Context) (string, error) {
		credential, err := store.Resolve(ctx, id)
		if err != nil {
			return "", classifyCredentialError(err)
		}
		mu.Lock()
		for _, value := range []string{credential.AccessToken, credential.RefreshToken} {
			found := false
			for _, known := range secrets {
				found = found || known == value
			}
			if !found && value != "" {
				secrets = append(secrets, value)
			}
		}
		mu.Unlock()
		return credential.AccessToken, nil
	}
	p.Secrets = func() []string { mu.Lock(); defer mu.Unlock(); return append([]string(nil), secrets...) }
	return nil
}

func classifyCredentialError(err error) error {
	var auth *kimi.Error
	if !errors.As(err, &auth) {
		return err
	}
	kind := agent.ErrorProvider
	switch auth.Kind {
	case "network":
		kind = agent.ErrorTransport
	case "unavailable":
		kind = agent.ErrorUnavailable
	case "rate_limit":
		kind = agent.ErrorRateLimit
	}
	if auth.Status >= 100 && auth.Status <= 599 {
		err = errors.Join(err, &modelwire.HTTPError{Status: auth.Status})
	}
	return &agent.ModelError{Kind: kind, Err: err}
}

func (p *Client) CredentialValues() []string {
	values := []string{p.Token}
	if p.Secrets != nil {
		values = append(values, p.Secrets()...)
	}
	return values
}
