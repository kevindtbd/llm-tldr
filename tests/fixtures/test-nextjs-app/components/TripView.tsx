// JSX component usage fixture
// <SlotCard /> and <Counter /> should create call edges

import { SlotCard } from "@/components/SlotCard";
import { Counter } from "@/components/Counter";

export function TripView() {
  return (
    <div>
      <SlotCard slot={{ id: "1" }} />
      <Counter initial={5} />
      <span>plain html</span>
    </div>
  );
}
