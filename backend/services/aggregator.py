from backend.db.models import AuctionListing


def compute_auction_stats(listings: list[AuctionListing]) -> dict:
    """Compute aggregate statistics from auction listings."""
    if not listings:
        return {}

    sold = [l for l in listings if l.is_sold and l.sold_price]
    unsold = [l for l in listings if not l.is_sold]

    sold_prices = [l.sold_price for l in sold]
    bid_counts = [l.bid_count for l in listings if l.bid_count is not None]

    stats = {
        "total_listings": len(listings),
        "total_sold": len(sold),
        "total_unsold": len(unsold),
        "sell_through_rate": round(len(sold) / len(listings) * 100, 1) if listings else 0,
    }

    if sold_prices:
        stats["avg_sold_price"] = round(sum(sold_prices) / len(sold_prices), 2)
        stats["min_sold_price"] = min(sold_prices)
        stats["max_sold_price"] = max(sold_prices)
        stats["median_sold_price"] = _median(sold_prices)

    if bid_counts:
        stats["avg_bids"] = round(sum(bid_counts) / len(bid_counts), 1)

    auction_days = [l.auction_days for l in listings if l.auction_days is not None]
    if auction_days:
        stats["avg_auction_days"] = round(sum(auction_days) / len(auction_days), 1)

    return stats


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 2)
