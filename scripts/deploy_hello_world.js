require("dotenv").config();

async function main() {
  const greeting = process.env.HELLO_WORLD_GREETING || "Hello Monad";
  const [deployer] = await hre.ethers.getSigners();

  console.log("Deploying HelloWorld with:", deployer.address);
  console.log("Greeting:", greeting);

  const factory = await hre.ethers.getContractFactory("HelloWorld");
  const contract = await factory.deploy(greeting);
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("HelloWorld deployed to:", address);
  console.log("Verification has been disabled for this hackathon build.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

