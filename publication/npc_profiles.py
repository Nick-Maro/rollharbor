"""Original synthetic profile demonstrating validated NPC action plans.

This is a software example, not a published creature's stat block. A DM must
verify a real creature and register its source before using it in a campaign.
"""

NPC_MULTIATTACK_PROFILES = {
    "demo_guard_longsword": {
        "actor_id": "npc_demo_guard",
        "source": "Original synthetic demo profile",
        "name": "Multiattacco dimostrativo",
        "weapon_names": ("spada lunga", "longsword"),
        "attacks": [
            {"name": "Spada lunga", "bonus": 3, "damage": "1d8+1", "melee": True},
            {"name": "Spada lunga", "bonus": 3, "damage": "1d8+1", "melee": True},
        ],
    },
}
