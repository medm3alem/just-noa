# NAO Robot Connection Guide

This guide explains how to connect Just Nao to a physical
NAO robot and change its IP address when necessary.

## 1. Network requirements

- The PC and NAO must be able to communicate over the network.
- NAOqi uses TCP port 9559.
- The Just Nao bridge uses TCP port 8766.
- Choregraphe 2.8 is used with the current bridge.

## 2. Find the robot IP address

NAO's IP address may change after restarting or switching Wi-Fi.

To find the current IP address:

1. Power on NAO and wait for startup.
2. Briefly press the chest button.
3. NAO may announce its IP address.
4. Alternatively, check the connection in Choregraphe.

## 3. Check the network connection

Open PowerShell and run:

    Test-NetConnection 192.168.2.121 -Port 9559

Replace the address with the current robot IP.

Expected result:

    TcpTestSucceeded : True

## 4. Start the Just Nao bridge

1. Open Choregraphe 2.8.
2. Connect to the physical NAO.
3. Start the Just Nao bridge v3.

Verify that port 8766 is reachable:

    Test-NetConnection 192.168.2.121 -Port 8766

The bridge must listen on a network interface accessible
from the computer.

## 5. Launch Just Nao

Open PowerShell in the project directory.

Example command:

    python main.py --choregraphe --ip 192.168.2.121 --bridge-port 8766 --ui hmi --video 0

## 6. Change the IP address

If NAO receives a new IP address, for example 192.168.1.105:

First, check connectivity:

    Test-NetConnection 192.168.1.105 -Port 9559
    Test-NetConnection 192.168.1.105 -Port 8766

Then launch the application with the new address:

    python main.py --choregraphe --ip 192.168.1.105 --bridge-port 8766 --ui hmi --video 0

No Python source code modification is required.

## 7. Troubleshooting

### Port 9559 unavailable

- Verify the IP address and Wi-Fi connection.
- Check that NAO is powered on and NAOqi is running.

### Port 8766 unavailable

- Verify that the bridge is running.
- Check the bridge host and port settings.
- Check network and firewall restrictions.

### NAO connects but does not move

- Check the Choregraphe logs.
- Verify the robot posture and awake state.
- Check for safety warnings.

## 8. Recommended setup

For demonstrations, consider configuring a DHCP reservation
on the Wi-Fi router to keep NAO's IP address consistent.

## 9. Safety

- Inspect NAO before physical tests.
- Use a flat and clear surface.
- Keep an operator nearby.
- Validate new dances at reduced speed first.
- Stop immediately if the robot becomes unstable.
