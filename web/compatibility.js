// Replace placeholders with confirmed minimum releases after client adaptation.
// Omit unsupported formats; do not infer compatibility from a client's latest version.
const clients = [
  { name: 'SATLI', bin: 'x.x.x', json: {} },
  { name: 'SATLI lite', json: { 1: 'x.x.x' } },
];

export function compatibleClients(variant) {
  return clients.flatMap(client => {
    const version = (variant.binPath && client.bin)
      || (variant.jsonPath && client.json[variant.jsonVersion]);
    return version ? [`${client.name} ${version}+`] : [];
  });
}
