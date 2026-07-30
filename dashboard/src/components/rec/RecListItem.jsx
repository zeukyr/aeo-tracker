import RecRow from "./RecRow";

// Thin wrapper kept for a single call shape across every list in this tab
// (Active, priority tiers, Pinned): a compact RecRow whose click navigates to
// the rec's own /recommendations/:id detail page - full card, own URL,
// shareable/bookmarkable - rather than expanding a full card in place, so
// none of these lists reflow or grow harder to scroll the more you open.
export default function RecListItem({ rec, onOpenDetail, onTogglePin }) {
  return <RecRow rec={rec} onOpenDetail={onOpenDetail} onTogglePin={onTogglePin} />;
}
