import httpx
from app.providers.base import Metric, ProviderAdapter, ProviderUsage

class DeepSeekAdapter(ProviderAdapter):
    id = "deepseek"
    name = "DeepSeek"
    description = "DeepSeek account balance."
    default_base_url = "https://api.deepseek.com"
    metric_names = ["available", "total_balance", "granted_balance", "topped_up_balance"]
    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/user/balance", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_usage(data)
    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        balances = data.get("balance_infos") or []
        preferred = next((i for i in balances if i.get("currency") == "USD"), balances[0] if balances else {})
        currency = preferred.get("currency", "")
        total = preferred.get("total_balance")
        granted = preferred.get("granted_balance")
        topped = preferred.get("topped_up_balance")
        available = bool(data.get("is_available"))
        metrics = [Metric("available", available), Metric("total_balance", float(total) if total is not None else None, currency), Metric("granted_balance", float(granted) if granted is not None else None, currency), Metric("topped_up_balance", float(topped) if topped is not None else None, currency)]
        status = "healthy" if available else "degraded"
        summary = f"{total} {currency} available" if total is not None else "DeepSeek balance fetched"
        return ProviderUsage(status=status, summary=summary, metrics=metrics, raw=data)
