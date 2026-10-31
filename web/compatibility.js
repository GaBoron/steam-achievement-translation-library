// Minimum released versions: SATLI introduced Catalog V2 in 2.1.0;
// SATLI lite introduced format 1 in 0.1.0 and standalone format 2 in 0.2.0.
// Omit unsupported formats until a compatible client release is available.
const clients = [
  { name: 'SATLI', bin: '2.1.0', json: {} },
  { name: 'SATLI lite', json: { 1: '0.1.0', 2: '0.2.0' } },
];

export function compatibleClients(variant) {
  return clients.flatMap(client => {
    const version = (variant.binPath && client.bin)
      || (variant.jsonPath && client.json[variant.jsonVersion]);
    return version ? [`${client.name} ${version}+`] : [];
  });
}
