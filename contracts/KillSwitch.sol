// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IERC20Like {
    function approve(address spender, uint256 amount) external returns (bool);
}

contract KillSwitch {
    enum TradeAction {
        Buy,
        Sell,
        Hold
    }

    error NotOwner();
    error ContractPaused();
    error InvalidTradeSize();
    error InvalidAction(uint8 action);
    error DailyCapExceeded(uint256 attempted, uint256 remaining);
    error PerTradeLimitExceeded(uint256 attempted, uint256 allowed);
    error CooldownActive(uint256 nextAllowedTimestamp);
    error InvalidTarget(address target);
    error TokenApproveFailed(address token, address spender, uint256 amount);
    error TargetCallFailed(bytes revertData);

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event PauseStateChanged(bool paused);
    event DailyCapUpdated(uint256 previousCap, uint256 newCap);
    event PerTradeLimitUpdated(uint256 previousLimit, uint256 newLimit);
    event CooldownUpdated(uint256 previousCooldown, uint256 newCooldown);
    event TokenApprovalSet(address indexed token, address indexed spender, uint256 amount);
    event TradePlaced(
        address indexed caller,
        uint8 indexed action,
        uint256 size,
        address indexed target,
        uint256 value,
        bytes4 selector,
        uint256 timestamp
    );

    address public owner;
    bool public paused;
    uint256 public dailyCap;
    uint256 public perTradeLimit;
    uint256 public cooldownSeconds;
    uint256 public periodStart;
    uint256 public tradedToday;
    uint256 public lastTradeTimestamp;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier whenNotPaused() {
        if (paused) revert ContractPaused();
        _;
    }

    constructor(
        uint256 initialDailyCap,
        uint256 initialPerTradeLimit,
        uint256 initialCooldownSeconds
    ) {
        owner = msg.sender;
        dailyCap = initialDailyCap;
        perTradeLimit = initialPerTradeLimit;
        cooldownSeconds = initialCooldownSeconds;
        periodStart = block.timestamp;
        emit OwnershipTransferred(address(0), owner);
    }

    receive() external payable {}

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidTarget(newOwner);
        address previousOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(previousOwner, newOwner);
    }

    function pause() external onlyOwner {
        paused = true;
        emit PauseStateChanged(true);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit PauseStateChanged(false);
    }

    function setDailyCap(uint256 newDailyCap) external onlyOwner {
        uint256 previousCap = dailyCap;
        dailyCap = newDailyCap;
        emit DailyCapUpdated(previousCap, newDailyCap);
    }

    function setPerTradeLimit(uint256 newPerTradeLimit) external onlyOwner {
        uint256 previousLimit = perTradeLimit;
        perTradeLimit = newPerTradeLimit;
        emit PerTradeLimitUpdated(previousLimit, newPerTradeLimit);
    }

    function setCooldown(uint256 newCooldownSeconds) external onlyOwner {
        uint256 previousCooldown = cooldownSeconds;
        cooldownSeconds = newCooldownSeconds;
        emit CooldownUpdated(previousCooldown, newCooldownSeconds);
    }

    function approveToken(address token, address spender, uint256 amount) external onlyOwner {
        if (token == address(0)) revert InvalidTarget(token);
        if (spender == address(0)) revert InvalidTarget(spender);

        _safeApprove(token, spender, 0);
        _safeApprove(token, spender, amount);

        emit TokenApprovalSet(token, spender, amount);
    }

    function remainingDailyCapacity() public view returns (uint256) {
        if (block.timestamp >= periodStart + 1 days) {
            return dailyCap;
        }

        if (tradedToday >= dailyCap) {
            return 0;
        }

        return dailyCap - tradedToday;
    }

    function canTrade(uint256 size) external view returns (bool, string memory) {
        if (paused) return (false, "paused");
        if (size == 0) return (false, "trade size is zero");
        if (size > perTradeLimit) return (false, "per-trade limit exceeded");

        uint256 remainingCap = remainingDailyCapacity();
        if (size > remainingCap) return (false, "daily cap exceeded");

        if (cooldownSeconds > 0 && lastTradeTimestamp != 0) {
            uint256 nextAllowedTimestamp = lastTradeTimestamp + cooldownSeconds;
            if (block.timestamp < nextAllowedTimestamp) {
                return (false, "cooldown active");
            }
        }

        return (true, "ok");
    }

    function executeTrade(
        uint8 action,
        uint256 size,
        address target,
        bytes calldata data
    ) external payable onlyOwner whenNotPaused returns (bytes memory result) {
        if (size == 0) revert InvalidTradeSize();
        if (action > uint8(TradeAction.Hold) - 1) revert InvalidAction(action);
        if (target == address(0)) revert InvalidTarget(target);

        _rolloverIfNeeded();

        if (size > perTradeLimit) revert PerTradeLimitExceeded(size, perTradeLimit);

        uint256 remainingCap = remainingDailyCapacity();
        if (size > remainingCap) revert DailyCapExceeded(size, remainingCap);

        if (cooldownSeconds > 0 && lastTradeTimestamp != 0) {
            uint256 nextAllowedTimestamp = lastTradeTimestamp + cooldownSeconds;
            if (block.timestamp < nextAllowedTimestamp) {
                revert CooldownActive(nextAllowedTimestamp);
            }
        }

        tradedToday += size;
        lastTradeTimestamp = block.timestamp;

        (bool success, bytes memory callResult) = target.call{value: msg.value}(data);
        if (!success) revert TargetCallFailed(callResult);

        emit TradePlaced(
            msg.sender,
            action,
            size,
            target,
            msg.value,
            _selectorFromCalldata(data),
            block.timestamp
        );

        return callResult;
    }

    function _rolloverIfNeeded() internal {
        if (block.timestamp >= periodStart + 1 days) {
            periodStart = block.timestamp;
            tradedToday = 0;
        }
    }

    function _safeApprove(address token, address spender, uint256 amount) internal {
        (bool success, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Like.approve.selector, spender, amount));
        if (!success || (data.length != 0 && !abi.decode(data, (bool)))) {
            revert TokenApproveFailed(token, spender, amount);
        }
    }

    function _selectorFromCalldata(bytes calldata data) internal pure returns (bytes4 selector) {
        if (data.length < 4) {
            return bytes4(0);
        }

        selector =
            bytes4(data[0]) |
            (bytes4(data[1]) >> 8) |
            (bytes4(data[2]) >> 16) |
            (bytes4(data[3]) >> 24);
    }
}
