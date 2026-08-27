from locust import HttpUser, task, between

class RAGUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def upload_pdf(self):
        with open("test_files/sample_50MB.pdf", "rb") as f:
            self.client.post("/chat/upload", files={"file": f}, data={"session_id": "test-session"})
