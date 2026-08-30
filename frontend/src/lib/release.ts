const gitSha = process.env.NEXT_PUBLIC_GIT_SHA || "unknown";
const rawBuildDate = process.env.NEXT_PUBLIC_BUILD_DATE || "unknown";

export const release = {
  version: process.env.NEXT_PUBLIC_APP_VERSION || "development",
  commit: gitSha,
  shortCommit: gitSha === "unknown" ? gitSha : gitSha.slice(0, 7),
  environment: process.env.NEXT_PUBLIC_ENVIRONMENT || "development",
  buildDate:
    rawBuildDate === "unknown"
      ? rawBuildDate
      : rawBuildDate.replace("T", " ").replace("Z", " UTC"),
} as const;
