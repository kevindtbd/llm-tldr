// Test file fixture: module-level describe/it with imported function calls
// These should create call edges from <module> to Counter

import { Counter } from "@/components/Counter";

describe("Counter", () => {
  it("starts at initial value", () => {
    const result = Counter({ initial: 5 });
    expect(result.count).toBe(5);
  });

  it("increments", () => {
    const result = Counter({ initial: 0 });
    result.handleIncrement();
    expect(result.count).toBe(1);
  });
});
