import type { TickerMarket } from "../../api";

const MARKET_LABEL: Record<TickerMarket, string> = {
  us: "US",
  hk: "HK",
  cn: "CN",
  other: "Other",
};

type Props = {
  market: TickerMarket;
};

export function MarketBadge({ market }: Props) {
  return (
    <span className="topics-market-badge" data-market={market}>
      {MARKET_LABEL[market] ?? market.toUpperCase()}
    </span>
  );
}
