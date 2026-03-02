// Bug 2 fixture: nested function declarations inside a component
// handleIncrement and handleReset should be extracted.

import { requireAuth } from "@/lib/helpers";

export function Counter({ initial = 0 }: { initial?: number }) {
  let count = initial;

  function handleIncrement() {
    count += 1;
  }

  function handleReset() {
    count = 0;
  }

  const handleDouble = () => {
    count *= 2;
  };

  return { count, handleIncrement, handleReset, handleDouble };
}
