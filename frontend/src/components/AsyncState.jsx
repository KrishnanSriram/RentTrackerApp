/** Loading spinner / error-with-retry wrapper for data loaded from the API. */
export default function AsyncState({ loading, error, onRetry, children }) {
  if (error) {
    return (
      <div className="alert-error">
        <span>{error.message}</span>
        {onRetry && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    )
  }
  if (loading) return <div className="loading">Loading…</div>
  return children
}
