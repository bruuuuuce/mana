# Canonical thread validation shared by mutation and read projection.
def valid_thread:
  type == "object" and .schemaVersion == "mana.human-feedback.thread/v1" and
    (.threadId|type == "string" and test("^thread_[0-9a-f]{64}$")) and
    (.revision|type == "string" and test("^[0-9]+$")) and
    (.target.artifactId|type == "string") and (.target.artifactRevision|type == "string") and
    (.state|IN("open","resolved")) and (.entries|type == "array") and
    all(.entries[]; (.entryId|type == "string") and (.author|type == "string") and (.body|type == "string") and (.kind|IN("comment","reply")));
