// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract MockTradeTarget {
    event TargetHit(address indexed caller, bytes payload, uint256 value);

    function perform(bytes calldata payload) external payable returns (bytes32) {
        emit TargetHit(msg.sender, payload, msg.value);
        return keccak256(payload);
    }
}

