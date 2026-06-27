// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract HelloWorld {
    string private greeting;

    event GreetingUpdated(string previousGreeting, string newGreeting);

    constructor(string memory initialGreeting) {
        greeting = initialGreeting;
    }

    function getGreeting() external view returns (string memory) {
        return greeting;
    }

    function setGreeting(string calldata newGreeting) external {
        string memory previousGreeting = greeting;
        greeting = newGreeting;
        emit GreetingUpdated(previousGreeting, newGreeting);
    }
}

