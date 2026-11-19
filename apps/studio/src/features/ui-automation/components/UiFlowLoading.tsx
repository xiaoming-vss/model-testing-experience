export function UiFlowLoading({ label }: { label: string }) {
  return <div className="ui-wb-pipeline ui-flow-loading flex min-h-[360px] flex-col gap-3 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3" role="status" aria-live="polite">
    <span className="ui-flow-loading-label text-xs text-[var(--srf-text-muted)]">{label}</span>
    <div className="ui-flow-loading-grid grid grid-cols-[repeat(auto-fill,180px)] content-start gap-5" aria-hidden="true">
      {Array.from({ length: 12 }, (_, index) => <span className="ui-flow-loading-card h-[86px] rounded-[8px] border border-[var(--srf-card-border)] bg-[linear-gradient(90deg,var(--srf-hover)_20%,var(--srf-card)_40%,var(--srf-hover)_60%)] bg-[length:300%_100%] animate-[ui-flow-loading-shimmer_1.4s_ease-in-out_infinite] motion-reduce:animate-none" key={index} />)}
    </div>
  </div>
}
