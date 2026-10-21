package execution

import b "pwnmesh/internal/board"

// ScheduleQuery selects admission from one caller-owned transaction snapshot.
// A nil Namespace requests the scheduling view without execution admission.
type ScheduleQuery struct {
	ProjectID       string
	Offset          int
	ExpectedVersion string
	Namespace       *string
}

func Schedule(t *b.Tx, input ScheduleQuery) (b.SchedulePage, error) {
	p, err := t.ScheduleInput(input.ProjectID, input.Offset, input.ExpectedVersion)
	if err == nil && input.Namespace != nil {
		namespace := *input.Namespace
		if namespace == "" || len(namespace) > 128 {
			err = b.Err(422, "namespace is required and must not exceed 128 bytes")
		}
		if err == nil {
			p.ExecutionChecks, err = t.ScheduleExecutionChecks(p.Project.ID, namespace, p.Steps)
		}
		if err == nil && input.Offset == 0 {
			// Control admission shares the scheduling snapshot. Return it once,
			// alongside Execute checks, instead of adding a round trip per role.
			for _, kind := range []string{"reason", "curate"} {
				key := p.RetryKey
				if kind == "curate" {
					if !p.CurationNeeded {
						continue
					}
					key = p.CurationRetryKey
				}
				check, checkErr := t.CheckExecutions(b.ExecutionCheckQuery{ProjectID: p.Project.ID, Namespace: namespace, Generation: p.Project.Generation, Kind: kind, RetryKey: key})
				if checkErr != nil {
					return b.SchedulePage{}, checkErr
				}
				p.ExecutionChecks[kind+":"] = check
			}
		}
	}
	return p, err
}
