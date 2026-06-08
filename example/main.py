from pythia import Server
import example.urls  # auto-discovery de todos os endpoints

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
