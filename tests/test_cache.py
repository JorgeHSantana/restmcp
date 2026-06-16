import time
from restmcp import cached_method


class Svc:
    def __init__(self):
        self.calls = 0

    @cached_method(ttl=60)
    def get(self, x):
        self.calls += 1
        return x * 10


def test_cacheia_por_args():
    s = Svc()
    assert s.get(1) == 10 and s.get(1) == 10
    assert s.calls == 1                 # 2ª chamada veio do cache
    assert s.get(2) == 20               # arg diferente -> chave diferente
    assert s.calls == 2


def test_ttl_expira():
    class S2:
        def __init__(self): self.calls = 0
        @cached_method(ttl=0.05)
        def get(self):
            self.calls += 1; return 1
    s = S2(); s.get(); time.sleep(0.07); s.get()
    assert s.calls == 2


def test_cacheia_args_nao_hashaveis():
    """Caso motivador da issue: Repository.get(id_list=[...]). list NÃO é
    hashável — uma chave baseada em hash/tuple quebra com TypeError aqui."""
    class S3:
        def __init__(self): self.calls = 0
        @cached_method(ttl=60)
        def get(self, ids):
            self.calls += 1
            return sum(ids)
    s = S3()
    assert s.get([1, 2, 3]) == 6
    assert s.get([1, 2, 3]) == 6        # 2ª veio do cache, SEM "unhashable type: 'list'"
    assert s.calls == 1
    assert s.get([1, 2]) == 3           # lista diferente -> chave diferente
    assert s.calls == 2
