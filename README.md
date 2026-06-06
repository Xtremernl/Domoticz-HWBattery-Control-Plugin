#HW-Battery-Control-plugin
A Python plugin for Domoticz that creates several devices for the HomeWizard Battery Controller (P1 Device).

The plugin configuration requires the ip of the P1 Device and a token.
A token is created on the battery using the `activate_user.py` script.
The script initiates the token generation protocol as described in https://api-documentation.homewizard.com/docs/v2/authorization.
To run it provide the ip of the P1 device and an username as an argument.
It asks the user to press enter after the P1 device has been put in token generation mode, by touching the LED button on the P1 device itself.
When a token is acquired successfully the script prints the token returned as well as some device and user information.

The ip of the P1 (and the battery('s)) device can be found by running the python3 detect.py script with no command line options.
It should print the type of all HomeWizard devices on your network, along with their ip address.
Press the enter key to stop the program.
Note: Each time the battery receives a new ip address, the token must be renewed. To avoid having to generate tokens frequently, you may want to assign the battery a static ip address.

You may want to test the connection. Edit the ip and token in test.py and run it, also without command line options. It should be active for about 2 minutes, while printing the changed state of the battery device every 10 seconds.

Notes:

Make sure to run pip install -r requirements before running the above python scripts.
On Macos the python commands may fail to run due to insufficient authorisation. Run sudo python3 <command> instead.
