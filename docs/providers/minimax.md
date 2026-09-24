# MiniMax Token Plan

Usage Dashboard supports **MiniMax Token Plan** quota monitoring. This adapter is subscription-only: it uses a MiniMax **Token Plan Subscription Key**, not a normal MiniMax PAYG API key, and does not report PAYG billing or balance.

## Setup

1. Open the MiniMax Token Plan or subscription area.
2. Create or copy a Token Plan Subscription Key.
3. In **Settings → Connected providers**, select **MiniMax**, paste the Subscription Key, and choose **Subscription** billing. Configure your actual subscription amount, currency, cadence, and billing anchor if you use subscription economics.

The key is encrypted at rest. It is sent only as a Bearer credential to MiniMax's configured base URL. The default request is:

```http
GET https://www.minimax.io/v1/token_plan/remains
Authorization: Bearer <TOKEN_PLAN_SUBSCRIPTION_KEY>
Content-Type: application/json
```

The base URL remains configurable for supported official MiniMax endpoints.

## Quota telemetry

MiniMax returns resource groups in `model_remains`; `general` is used for the provider-level coding/chat view when available. Other groups, such as `video`, are retained as resource-group data and are not combined into the general quota percentage. If `general` is absent, the first valid group is used safely.

The dashboard exposes the provider-authoritative rolling **5-hour** and **weekly** remaining percentages, then derives used percentage as `100 - remaining`. Zero count fields do not hide percentage telemetry. Absolute `end_time` and `weekly_end_time` timestamps are used as reset times when present; no reset is manufactured from incomplete data.

A status of `2` or zero remaining on a limited quota marks the provider exhausted. Status `3` is treated as unlimited and is not exhausted merely because count fields are `0/0`.

## Billing scope

MiniMax's published Plus, Max, and Ultra monthly token figures are plan metadata, not live `/v1/token_plan/remains` monthly telemetry. Usage Dashboard does not fabricate a monthly quota, reset, remaining balance, or monetary usage from them. Configure subscription economics separately with your actual billing details; Token Plan remaining percentages are never treated as currency.

## Errors

MiniMax may return business errors in an HTTP 200 response. The adapter requires `base_resp.status_code == 0`; authentication, missing active subscriptions, rate limits, malformed responses, and upstream/network failures are normalized without exposing the Subscription Key.
