import json
import numbers

def get_endpoint_from_round_robin(config: json, index_ref: json) -> str:
    use_edge_tts = config.get('use_edge_tts_service', False)
    api_from = "api" if not use_edge_tts else "edge_tts_api"

    default_host = config[api_from]["host"]
    round_robin_hosts = config[api_from]["host_round_robin"]

    speech_endpoint = config[api_from]["endpoints"]["speech"]

    round_robin_host_count = len(round_robin_hosts)

    selected_host = default_host

    if round_robin_host_count > 1:
        index = index_ref.get('current')
        selected_host = round_robin_hosts[index]
        index += 1
        index = 0 if round_robin_host_count <= index else index
        index_ref.update({"current": index})

    return selected_host + speech_endpoint


