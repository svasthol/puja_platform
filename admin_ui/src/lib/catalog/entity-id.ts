/** Encode SMALLINT category PK as UUID for puja_media.entity_id (backend §20). */
export function categoryEntityUuid(categoryId: number): string {
  const hex = BigInt(categoryId).toString(16).padStart(32, "0");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
