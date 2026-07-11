# slack-lambda module

Packages and deploys the ack + worker Lambdas (Python 3.13). Ack gets a public
Function URL (auth NONE — verified in-handler). Worker async failures route to an
SQS DLQ. Log groups have explicit retention. Requires the `archive` provider.

## Inputs

In addition to the interface described in the design doc, this module takes
`worker_role_name` — the bare IAM role name (not ARN) of the worker Lambda's
execution role, e.g. `module.iam.worker_role_name`. It's used directly as the
`role` argument on the worker's DLQ-send inline policy, instead of deriving the
role name from `worker_role_arn` via `split()`.
