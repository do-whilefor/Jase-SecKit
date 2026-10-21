package modelcontrol_test

import (
	"net/http"
	"testing"

	"pwnmesh/internal/modelconfig"
	"pwnmesh/internal/provider"
)

func TestSubscriptionSettingsUseTransportEndpointResolution(t *testing.T) {
	for _, tc := range []struct{ mode, base, endpoint string }{
		{"kimi_oauth", "https://api.kimi.com/coding", "https://api.kimi.com/coding/v1/messages"},
		{"glm_coding_plan", "https://open.bigmodel.cn/api/anthropic", "https://open.bigmodel.cn/api/anthropic/v1/messages"},
	} {
		t.Run(tc.mode, func(t *testing.T) {
			for _, base := range []string{tc.base, tc.base + "/v1", tc.endpoint} {
				settings := modelconfig.Defaults(func(string) string { return "" })
				settings.AuthMode, settings.BaseURL = tc.mode, base
				if err := settings.Validate(false); err != nil {
					t.Fatalf("transport-supported endpoint %q rejected by settings: %v", base, err)
				}
				settings.BaseURL = "https://untrusted.invalid/v1/messages"
				if err := settings.Validate(false); err == nil {
					t.Fatal("subscription credential accepted an untrusted endpoint")
				}
			}
		})
	}
}

func TestUnspecifiedConnectionModeIsDirect(t *testing.T) {
	t.Setenv("HTTP_PROXY", "http://proxy.invalid:8080")
	t.Setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
	for _, mode := range []string{"", "direct"} {
		client, err := provider.ConnectionClient(mode, "")
		if err != nil || client == nil {
			t.Fatalf("connection mode %q did not create an explicit direct transport: %v", mode, err)
		}
		defer client.CloseIdleConnections()
		transport, ok := client.Transport.(*http.Transport)
		if !ok || transport.Proxy != nil {
			t.Fatalf("connection mode %q inherited process proxy configuration", mode)
		}
	}
	client, err := provider.ConnectionClient("proxy", "http://proxy.invalid:8080")
	if err != nil {
		t.Fatal(err)
	}
	defer client.CloseIdleConnections()
	request, _ := http.NewRequest(http.MethodGet, "https://model.invalid", nil)
	proxy, err := client.Transport.(*http.Transport).Proxy(request)
	if err != nil || proxy.String() != "http://proxy.invalid:8080" {
		t.Fatalf("explicit proxy lost its configured endpoint: %v, %v", proxy, err)
	}
}
