package dispatcher

import "pwnmesh/internal/controlclient"

// Retain the construction types while the Scheduler consumes typed operations.
type Client = controlclient.Client
type ProtocolError = controlclient.ProtocolError
type Lease = controlclient.Lease
