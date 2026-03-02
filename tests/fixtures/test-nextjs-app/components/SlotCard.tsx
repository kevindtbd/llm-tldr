// Simple component fixture — target of JSX usage

export function SlotCard({ slot }: { slot: { id: string } }) {
  return <div>{slot.id}</div>;
}
