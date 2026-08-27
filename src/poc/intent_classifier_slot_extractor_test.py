class IntentClassifierExtractor:
    def __init__(self):
        pass

    def classify_extract(self, messages):

        return None

if __name__ == "__main__":
    messages = [{"message_id":"msg_002",
                 "sender_id": "u00001",
                 "sender_type":"user",
                 "content": "Hi, I want to change the delivery address for my last order",
                 "message_timestamp": "2026-08-23T12:40:15Z"},
                { "message_id":"msg_003",
                  "sender_id": "support-team-v1",
                  "sender_type":"support-team",
                  "content": "I'm looking into it, is this the order O#00001 ?",
                  "message_timestamp": "2026-08-23T12:40:45Z"},
                { "message_id":"msg_004",
                  "sender_id": "u00001",
                  "sender_type":"user",
                  "content": "Yes",
                  "message_timestamp": "2026-08-23T12:41:00Z"},
                { "message_id":"msg_005",
                  "sender_id": "support-team-v1",
                  "sender_type":"support-team",
                  "content": "As the order O#00001 is not yet shipped, I can change the delivery address. Would you mention the new delivery address?",
                  "message_timestamp": "2026-08-23T12:41:15Z"},
                { "message_id":"msg_006",
                  "sender_id": "u00001",
                  "sender_type":"user",
                  "content": "New delivery address is Street 1, Satyam Park, 80 Feet Road, Rajkot 360003",
                  "message_timestamp": "2026-08-23T12:41:30Z"},
                { "message_id":"msg_007",
                  "sender_id": "support-team-v1",
                  "sender_type":"support-team",
                  "content": "Ok, I have updated the delivery address to Street 1, Satyam Park, 80 Feet Road, Rajkot 360003",
                  "message_timestamp": "2026-08-23T12:41:45Z"},
                ]

    intent_classifier_slot_extractor = IntentClassifierSlotExtractor()
    intent_classifier_slot_extractor.classify_extract(messages[:1])