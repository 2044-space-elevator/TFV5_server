from db.tool import Db 
import json
import time

class NotificationsDb(Db):
    def __init__(self, path : str, port_api : int):
        super().__init__(path, port_api, -1)
    
    def create_user_table(self, uid : int):
        uid = int(uid)
        cmd = """
    CREATE TABLE IF NOT EXISTS U{} (
        time_stamp REAL,
        info TEXT
    )
    """.format(uid)
        self.execute(cmd)

    def _serialize_event(self, event):
        if isinstance(event, (dict, list)):
            return json.dumps(event, ensure_ascii=False)
        return str(event)

    def _deserialize_event(self, raw_event : str):
        try:
            event = json.loads(raw_event)
            if isinstance(event, dict):
                return event
            return {"content" : event}
        except json.JSONDecodeError:
            return {"content" : raw_event}

    def query_events_after(self, uid : int, time_stamp : str):
        uid = int(uid)
        self.create_user_table(uid)
        return self.query("SELECT * FROM U{} WHERE time_stamp > ? ORDER BY time_stamp ASC".format(uid), (time_stamp,))

    def query_all_events(self, uid : int):
        return self.query_events_after(uid, 0)

    def list_events_after(self, uid : int, time_stamp : str):
        events = []
        for item_time_stamp, raw_event in self.query_events_after(uid, time_stamp):
            event = self._deserialize_event(raw_event)
            event["time_stamp"] = item_time_stamp
            events.append(event)
        return events

    def list_all_events(self, uid : int):
        return self.list_events_after(uid, 0)

    def serialize_rows(self, rows):
        serialized = []
        for time_stamp, raw_event in rows:
            event = self._deserialize_event(raw_event)
            serialized.append({"time_stamp" : time_stamp, "info" : event})
        return serialized

    def add_event(self, uid : int, event : str):
        uid = int(uid)
        self.create_user_table(uid)
        event_time_stamp = time.time()
        self.execute(
            "INSERT INTO U{} (time_stamp, info) VALUES (?, ?)".format(uid),
            (event_time_stamp, self._serialize_event(event))
        )
        return event_time_stamp

    def delete_events_before(self, uid : int, time_stamp : str):
        uid = int(uid)
        self.create_user_table(uid)
        self.execute("DELETE FROM U{} WHERE time_stamp <= ?".format(uid), (time_stamp,))
        return True

    def delete_all_events(self, uid : int):
        uid = int(uid)
        self.create_user_table(uid)
        self.execute("DELETE FROM U{}".format(uid))
        return True

    def delete_user_table(self, uid : int):
        uid = int(uid)
        self.execute("DROP TABLE IF EXISTS U{}".format(uid))
        return True