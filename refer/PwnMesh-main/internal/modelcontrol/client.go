// Package modelcontrol carries private runtime configuration over the active
// Dispatcher's ownership channel. Public browser settings stay credential-free.
package modelcontrol

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"pwnmesh/internal/kimi"
	"pwnmesh/internal/modelconfig"
)

const SettingsPath = "/internal/model-settings"
const TokenPath = "/internal/model-token"
const TokenEnv = "PWNMESH_CONTROL_TOKEN"

type Snapshot struct {
	Settings modelconfig.Settings `json:"settings"`
	Found    bool                 `json:"found"`
}

type TokenRequest struct {
	CredentialID   string `json:"credential_id"`
	ConnectionMode string `json:"connection_mode"`
	ProxyURL       string `json:"proxy_url"`
}

type TokenResponse struct {
	Token string `json:"token"`
}

type Client struct {
	Base, Namespace, Holder, Installation string
	ControlToken                          string
	HTTP                                  *http.Client
}

func (c *Client) call(ctx context.Context, path string, input, output any) error {
	if c == nil || len(c.ControlToken) < 32 || len(c.Holder) != 32 || c.Namespace == "" || c.Installation == "" {
		return errors.New("model settings require active dispatcher ownership")
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(c.Base, "/")+path, bytes.NewReader(raw))
	if err != nil {
		return errors.New("invalid model control URL")
	}
	req.Header.Set("Authorization", "Bearer "+c.ControlToken)
	req.Header.Set("X-PwnMesh-Dispatcher", c.Holder)
	req.Header.Set("X-PwnMesh-Namespace", c.Namespace)
	req.Header.Set("X-PwnMesh-Installation", c.Installation)
	req.Header.Set("Content-Type", "application/json")
	h := http.Client{Timeout: 40 * time.Second}
	if c.HTTP != nil {
		h = *c.HTTP
	}
	h.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	res, err := h.Do(req)
	if err != nil {
		return errors.Join(&kimi.Error{Kind: "network"}, ctx.Err())
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		// Never include response bodies, endpoint credentials or bearer tokens
		// in scheduling logs. OAuth classifications remain useful for recovery.
		if path == TokenPath {
			var failure struct {
				Kind   string `json:"kind"`
				Status int    `json:"status"`
			}
			if json.NewDecoder(io.LimitReader(res.Body, 1024)).Decode(&failure) == nil {
				switch failure.Kind {
				case "network", "unavailable", "rate_limit", "login_required", "storage":
					return &kimi.Error{Kind: failure.Kind, Status: failure.Status}
				}
			}
			if res.StatusCode >= 500 {
				return &kimi.Error{Kind: "unavailable", Status: res.StatusCode}
			}
			if res.StatusCode == 429 {
				return &kimi.Error{Kind: "rate_limit", Status: res.StatusCode}
			}
		}
		return fmt.Errorf("model control request rejected (HTTP %d)", res.StatusCode)
	}
	raw, err = io.ReadAll(io.LimitReader(res.Body, (32<<10)+1))
	if err != nil {
		return errors.Join(&kimi.Error{Kind: "network"}, ctx.Err())
	}
	if len(raw) > 32<<10 || json.Unmarshal(raw, output) != nil {
		return errors.New("invalid model control response")
	}
	return nil
}

func (c *Client) Settings(ctx context.Context) (modelconfig.Settings, bool, error) {
	var snapshot Snapshot
	err := c.call(ctx, SettingsPath, struct{}{}, &snapshot)
	if err == nil && snapshot.Found {
		err = snapshot.Settings.Validate(false)
	}
	return snapshot.Settings, snapshot.Found, err
}

func (c *Client) Token(ctx context.Context, input TokenRequest) (string, error) {
	var result TokenResponse
	if err := c.call(ctx, TokenPath, input, &result); err != nil {
		return "", err
	}
	if strings.TrimSpace(result.Token) == "" || len(result.Token) > 8192 || strings.ContainsAny(result.Token, "\r\n\x00") {
		return "", errors.New("invalid model control token")
	}
	return result.Token, nil
}
