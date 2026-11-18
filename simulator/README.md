# Virtual sensor nodes

Until the ESP32 firmware exists, these processes **are** the sensing layer. Each node runs as its
own process, reads simulated sensors (daily cycle, noise, smoke physics, solar battery), decides
NORMAL / ALERT / FIRE on board, and publishes signed telemetry and events over MQTT using exactly
the contract in `contracts/` — the backend cannot tell them from real nodes.

```bash
python -m wamidh_sim.provision --count 5   # install 5 nodes at the top-ranked sites (keys!)
python -m wamidh_sim.run                   # start them (one process each) + the world process
python -m wamidh_sim.ignite 3              # a fire starts next to node 3
python -m wamidh_sim.ignite 3 --out        # ... is put out
python -m wamidh_sim.ignite 5 --power off  # node 5 loses power
python -m wamidh_sim.ignite --list         # state of every node
```

Each virtual node also has a **placeholder on-node camera** (ADR 0001, `camera.py`): it sleeps in NORMAL and, in ALERT and FIRE, looks and feeds what it sees into the node's `fire_prob`. By day it sees smoke and flames, at night only flames; it never sees fog. Neither the image nor the camera's result leaves the node.

Timing in `config/demo.yaml` is shortened for demos (NORMAL every 10 s); field values are in
`contracts/mqtt_topics.md`. The fire classifier is a rule-based placeholder for the TinyML model.

**The world process** (`wamidh_sim.world`, started by `run`) plays the physical effect of the
crews: when an incident is marked *under control*, *closed* or *false alarm*, it puts out the fire
around that incident's sensors. The nodes then sense clean air and report NORMAL by themselves —
the backend never overrides what a sensor reports.
