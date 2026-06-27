require("dotenv").config();

async function main() {
  const config = {
    dailyCap: process.env.KILLSWITCH_DAILY_CAP || "500",
    perTradeLimit: process.env.KILLSWITCH_PER_TRADE_LIMIT || "100",
    cooldownSeconds: Number(process.env.KILLSWITCH_COOLDOWN_SECONDS || "300")
  };

  const [deployer] = await hre.ethers.getSigners();
  const dailyCap = hre.ethers.parseUnits(config.dailyCap, 18);
  const perTradeLimit = hre.ethers.parseUnits(config.perTradeLimit, 18);

  console.log("Deploying KillSwitch with:", deployer.address);
  console.log("Config:", {
    dailyCap: config.dailyCap,
    perTradeLimit: config.perTradeLimit,
    cooldownSeconds: config.cooldownSeconds
  });

  const factory = await hre.ethers.getContractFactory("KillSwitch");
  const contract = await factory.deploy(dailyCap, perTradeLimit, config.cooldownSeconds);
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("KillSwitch deployed to:", address);
  console.log("Constructor args:", {
    dailyCap: dailyCap.toString(),
    perTradeLimit: perTradeLimit.toString(),
    cooldownSeconds: config.cooldownSeconds
  });
  console.log("Verification has been disabled for this hackathon build.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

