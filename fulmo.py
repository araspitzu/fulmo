from lightning import LightningRpc
from flask import Flask, request, render_template
import random
import qrcode
import json
import re
import ast
app = Flask(__name__)

# Connect to local LN node
ln = LightningRpc("/tmp/lightning-rpc")

@app.route("/")
def fulmo():
	return render_template('index.html')

@app.route("/newaddr/")
def new_address():
	bech32 = request.args.get('type')
	addr = ln.newaddr(bech32)
	return addr['address'] + qr(addr['address'])

@app.route("/getinfo/")
def get_info():
	info = {}
	get_info = ln.getinfo()
	info["Network"] = get_info["network"]
	info["Port"] = get_info["port"]
	info["Version"] = get_info["version"]
	info["Block Height"] = get_info["blockheight"]
	info["Lightning Node ID"] = get_info["id"]
	info["On-Chain Balance"] = str(int(list_funds()) * 0.00000001) + " BTC"
	
	json_data = json.dumps(info)
        return json_data	

@app.route("/listfunds/")
def list_funds():
	balance = 0;
	funds = ln.listfunds()
	for item in funds['outputs']:
		balance = balance + item["value"]
	
	return str(balance)

@app.route("/invoice/")
def invoice():
	make_qr = request.args.get("qr")
	satoshis = request.args.get("amount")
	description = request.args.get("description")
	invoice = ln.invoice(satoshis, "lbl{}".format(random.random()), description)
	bolt11 = str(invoice["bolt11"])
	if make_qr is not None:
		return bolt11 + qr("lightning:" + bolt11)
	else:
		return bolt11

@app.route("/bolt11/<action>")
def bolt11(action):
	bolt11 = request.args.get("bolt11")
	
	try:
		if action == "pay":
			result = ln.pay(bolt11)
		elif action == "decode":
			result = ln.decodepay(bolt11)
		else:
			result = {"error": "bad action"}	

	except ValueError, e:
		result = parse_exception(e)

	return json.dumps(result)

@app.route("/help/")
def help():
	help_result = ln.help()
	return json.dumps(help_result)

@app.route("/listchannels/")
def list_channels():
	peers = ln.listpeers()
	data = {}
	total_balance = 0
		
	# Relevant peers are ones that we have an open channel with, 
	# or we're still negotiation a channel with.
	# If our only relationship to a peer is that we have a closed channel, 
	# then we don't care about him for now.
	relevant_peer = {}

	# loop through all peers
	# get either the peer state, or channel state (if it exists)
	for key, value in peers.iteritems():
		for i, val in enumerate(value):
			data[i] = {}
			relevant_peer[i] = False

			if "alias" in val:
				data[i]["alias"] = val["alias"]

			data[i]["peer_id"] = val["id"]
			
			# If there is a state key in the peer dict, 
			# that means there is no channel yet, so just use that.
			# Otherwise, loop through the channels to get their states
			if "state" in val:
				# We have a current state with this peer, so he is relevantt
				relevant_peer[i] = True
				data[i]["state"] = val["state"]
			else:
				for j, channels in enumerate(val["channels"]):
					data[i][j] = {}

					# ONCHAIN means the channel is closed
					# So if the channel state is not "ONCHAIN",
					# then this peer is relevant.
					if channels["state"] != "ONCHAIN":
						relevant_peer[i] = True
						data[i][j]["channel_id"] = channels["channel_id"]
						data[i][j]["balance"] = channels["msatoshi_to_us"]
						data[i][j]["state"] = channels["state"]
						total_balance = total_balance + channels["msatoshi_to_us"]
			
			# If the peer is irrelevant, just remove him from the list
			if not relevant_peer[i]:
				del data[i]

			if total_balance > 0:
				data["balance"] = total_balance
				
	json_data = json.dumps(data)
	return json_data

@app.route("/connect/")
def connect():
	satoshis = request.args.get("satoshis")
	connection_string = request.args.get("c")
	if re.search(r".*@[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*:[0-9]*", connection_string) is None:
		return "Node must be in this format: NodeID@IPaddress:Port"
	
	node_id = connection_string[:connection_string.find("@")]
	ip = connection_string[connection_string.find("@")+1:connection_string.find(":")]
	port = connection_string[connection_string.find(":")+1:]

	try:
		connect = ln.connect(node_id, ip, port)
		result = fundChannel(connect["id"], satoshis)
	except ValueError, e:
		result = parse_exception(e)

        return json.dumps(result)

@app.route("/close/")
def close():
	channel_id = request.args.get("channel_id")
	
	try:
		result = ln.close(channel_id)
	except ValueError, e:
		result = parse_exception(e)

        return json.dumps(result)

def fund_channel(node_id, satoshis):
	fund_result = ln.fundchannel(node_id, satoshis)
	return str(fund_result)

def qr(data): 
	img = qrcode.make(data)
	filename = "static/qrcodes/" + data + ".png"
	img.save(filename)
	return str("<br /><img src='/" + filename + "'height='200' width='200'/>")

def parse_exception(e):
	# The ValueError that's thrown from the Lightning RPC library
	# contains (among other text) a string representation of a dict object.
	# This is a little hacky, but the goal here is to extract that dict
	# and return it, so it can be used as an actual dict, not a string
	error = str(e)
	msg_str = error[error.find("{"):error.find("}")+1]
	return ast.literal_eval(msg_str)

if __name__ == "__main__":
	app.run(host="192.168.0.100",ssl_context='adhoc')
