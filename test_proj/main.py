from pythia import Server
import urls  # auto-discovery

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
