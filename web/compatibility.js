// Minimum released versions: SATLI introduced Catalog V2 in 2.1.0;
// SATLI lite has supported format 1 since its first release, 0.1.0.
// Omit unsupported formats until a compatible client release is available.
const clients = [
  { name: 'SATLI', bin: '2.1.0', json: {} },
  { name: 'SATLI lite', json: { 1: '0.1.0' } },
];

export function compatibleClients(variant) {
  return clients.flatMap(client => {
    const version = (variant.binPath && client.bin)
      || (variant.jsonPath && client.json[variant.jsonVersion]);
    return version ? [`${client.name} ${version}+`] : [];
  });
}
