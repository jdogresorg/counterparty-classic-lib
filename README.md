# Description
`counterparty-classic-lib` is the reference implementation of the [Counterparty Protocol](https://counterparty.io).

**Note:** for the command-line interface to `counterparty-classic-lib`, see [`counterparty-classic-cli`](https://github.com/jdogresorg/counterparty-classic-cli).


# Installation

**WARNING** Master branch should only be used for testing. For production releases uses tagged releases.

For a simple Docker-based install of the Counterparty software stack, see [this guide](http://counterparty.io/docs/federated_node/).


# Manual installation

Download the latest [Bitcoin Core](https://github.com/bitcoin/bitcoin/releases) and create
a `bitcoin.conf` file with the following options:

```
rpcuser=bitcoinrpc
rpcpassword=rpc
server=1
txindex=1
rpctimeout=300
zmqpubhashblock=tcp://127.0.0.1:28832
zmqpubhashtx=tcp://127.0.0.1:28832
addresstype=legacy
```
**Note:** you can and should replace the RPC credentials. Remember to use the changed RPC credentials throughout this document.

Download and install latest addrindexrs:
```
$ git clone https://github.com/jdogresorg/counterparty-classic-addrindexrs.git
$ cd addrindexrs
$ cargo check
 -- Setup the appropiate environment variables --
  - ADDRINDEXRS_JSONRPC_IMPORT=1
  - ADDRINDEXRS_TXID_LIMIT=15000
  - ADDRINDEXRS_COOKIE=user:password
  - ADDRINDEXRS_INDEXER_RPC_ADDR=0.0.0.0:8432
  - ADDRINDEXRS_DAEMON_RPC_ADDR=bitcoin:8332
 --
$ cargo build --release
$ cargo run --release
```

You could run the indexd daemon with a process manager like `forever` or `pm2` (recommended).

Then, download and install `counterparty-classic-lib`:

```
$ git clone https://github.com/jdogresorg/counterparty-classic-lib.git
$ cd counterparty-classic-lib
$ sudo pip3 install --upgrade -r requirements.txt
$ sudo python3 setup.py install
```

Followed by `counterparty-classic-cli`:

```
$ git clone https://github.com/jdogresorg/counterparty-classic-cli.git
$ cd counterparty-classic-cli
$ sudo pip3 install --upgrade -r requirements.txt
$ sudo python3 setup.py install
```

Note on **sudo**: both counterparty-classic-lib and counterparty-server can be installed by non-sudoers. Please refer to external documentation for instructions on using pip without root access and other information related to custom install locations.


Then, launch the daemon via:

```
$ counterparty-server bootstrap
$ counterparty-server --backend-password=rpc start
```

# Basic Usage

## Via command-line

(Requires `counterparty-classic-cli` to be installed.)

* The first time you run the server, you may bootstrap the local database with:
	`$ counterparty-server bootstrap`

* Start the server with:
	`$ counterparty-server start`

* Check the status of the server with:
	`$ counterparty-client getinfo`

* For additional command-line arguments and options:
	`$ counterparty-server --help`
	`$ counterparty-client --help`

## Via Python

Bare usage from Python is also possible, without installing `counterparty-classic-cli`:

```
$ python3
>>> from counterpartylib import server
>>> db = server.initialise(<options>)
>>> server.start_all(db)
```

# Configuration and Operation

The paths to the **configuration** files, **log** files and **database** files are printed to the screen when starting the server in ‘verbose’ mode:
	`$ counterparty-server --verbose start`

By default, the **configuration files** are named `server.conf` and `client.conf` and located in the following directories:

* Linux: `~/.config/counterparty/`
* Windows: `%APPDATA%\Counterparty\`

Client and Server log files are named `counterparty.client.[testnet.]log` and `counterparty.server.[testnet.]log`, and located in the following directories:

* Linux: `~/.cache/counterparty/log/`
* Windows: `%APPDATA%\Local\Counterparty\counterparty\Logs`

Counterparty API activity is logged in `server.[testnet.]api.log` and `client.[testnet.]api.log`.

Counterparty database files are by default named `counterparty.[testnet.]db` and located in the following directories:

* Linux: `~/.local/share/counterparty`
* Windows: `%APPDATA%\Roaming\Counterparty\counterparty`

## Configuration File Format

Manual configuration is not necessary for most use cases. "back-end" and "wallet" are used to access Bitcoin server RPC.

A `counterparty-server` configuration file looks like this:

	[Default]
	backend-name = indexd
	backend-user = <user>
	backend-password = <password>
	indexd-connect = localhost
	indexd-port = 8432
	rpc-host = 0.0.0.0
	rpc-user = <rpcuser>
	rpc-password = <rpcpassword>

The ``force`` argument can be used either in the server configuration file or passed at runtime to make the server keep running in the case it loses connectivity with the Internet and falls behind the back-end database. This may be useful for *non-production* Counterparty servers that need to maintain RPC service availability even when the backend or counterparty server has no Internet connectivity.

A `counterparty-client` configuration file looks like this:

	[Default]
	wallet-name = bitcoincore
	wallet-connect = localhost
	wallet-user = <user>
	wallet-password = <password>
	counterparty-rpc-connect = localhost
	counterparty-rpc-user = <rpcuser>
	counterparty-rpc-password = <password>


# Developer notes

## Versioning

* Major version changes require a full (automatic) rebuild of the database.
* Minor version changes require a(n automatic) database reparse.
* All protocol changes are retroactive on testnet.
