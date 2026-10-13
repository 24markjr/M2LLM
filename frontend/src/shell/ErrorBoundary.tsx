/**
 * A page that fails shows why, and the rest of the console keeps working (Phase U5).
 *
 * Without it a rendering error anywhere unmounts the whole app and leaves a blank screen - which is
 * how a crash in the journal's replay was first seen. The boundary is keyed by the route in the
 * shell, so moving to another page clears it.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("page_failed", error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="page-error" role="alert">
        <h2>This page could not be shown</h2>
        <p>Nothing was lost: the investigation and its evidence are kept. Another page, or reloading this one, works.</p>
        <pre>{error.message}</pre>
        <button type="button" className="ui-button secondary" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
