const SEARCH_FIELDS = Object.freeze([
  'equipment_id',
  'event_equipment',
  'aliases',
  'equipment_type',
  'plant_location_id',
  'ecms_location_id',
]);

export function searchPlantViewEquipment(rows, query = '') {
  if (!Array.isArray(rows)) return [];
  const normalizedQuery = String(query).trim().toLowerCase();
  if (!normalizedQuery) return rows.slice();

  return rows.filter(row =>
    SEARCH_FIELDS.some(field => String(row?.[field] || '').toLowerCase().includes(normalizedQuery)),
  );
}

export function plantDrawingHref(row) {
  const equipment = row?.event_equipment || row?.equipment_id;
  if (!equipment) return '/drawing?view=plant';

  const params = new URLSearchParams({ equipment });
  if (row.plant_location_id) params.set('view', 'plant');
  else if (row.ecms_page) params.set('view', 'ecms');
  return `/drawing?${params.toString()}`;
}
