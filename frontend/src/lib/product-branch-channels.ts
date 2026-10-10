export type ProductBranchChannelFeatures = {
  counter: boolean;
  tables: boolean;
  commands: boolean;
};

type SalesChannel = "counter" | "table" | "command";

type ProductBranchChannelConfig = {
  is_available: boolean;
  available_counter: boolean;
  available_table: boolean;
  available_command: boolean;
  participates_in_service_fee: boolean | null;
  participates_in_commission: boolean | null;
};

const channelFeature: Record<SalesChannel, keyof ProductBranchChannelFeatures> = {
  counter: "counter",
  table: "tables",
  command: "commands",
};

export function visibleProductBranchChannels(features: ProductBranchChannelFeatures) {
  return (Object.keys(channelFeature) as SalesChannel[]).filter(
    (channel) => features[channelFeature[channel]],
  );
}

export function productBranchConfigPayload(
  config: ProductBranchChannelConfig,
  features: ProductBranchChannelFeatures,
) {
  const payload: {
    is_available: boolean;
    participates_in_service_fee: boolean | null;
    participates_in_commission: boolean | null;
    available_counter?: boolean;
    available_table?: boolean;
    available_command?: boolean;
  } = {
    is_available: config.is_available,
    participates_in_service_fee: config.participates_in_service_fee,
    participates_in_commission: config.participates_in_commission,
  };
  if (features.counter) payload.available_counter = config.available_counter;
  if (features.tables) payload.available_table = config.available_table;
  if (features.commands) payload.available_command = config.available_command;
  return payload;
}
