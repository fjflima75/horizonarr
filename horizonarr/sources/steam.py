"""Steam store prices (no key needed)."""
from .. import net


def price(appid, country="PT"):
    """{'final': 19.99, 'discount': 20, 'currency': 'EUR'}, {'free': True}, or None when not for sale."""
    d = net.request(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={country}"
                    f"&filters=price_overview", timeout=30)
    d = (d or {}).get(str(appid), {})
    if not d.get("success"):
        return None
    data = d.get("data") or {}
    if not data:  # success with no price block = free to play
        return {"free": True}
    po = data.get("price_overview")
    if not po:
        return None
    return {"final": po["final"] / 100, "discount": po["discount_percent"], "currency": po.get("currency", "EUR")}
