angular.module('deciframeApp').controller('SequenciaController', function($http, $window, ngProgressFactory, $anchorScroll, $location, GENEROS) {
  var COR_ACORDE = '#2E1C74';
  // espelha TAM_PAGINA do backend; a API nao devolve o total
  var TAM_PAGINA = 100;
  var vm = this;

  vm.sequenciasFamosas = [];
  vm.minhaSequencia = {};
  vm.isSearching = false;
  vm.showSearchResultsCount = false;
  vm.esfigeSpeech = "";
  vm.musics = [];
  vm.generos = GENEROS;
  vm.meuGenero = "";
  vm.progressbar = ngProgressFactory.createInstance();

  vm.pagina = 1;
  vm.temMais = false;
  vm.carregandoMais = false;
  vm.erroMais = "";
  // descarta respostas de buscas antigas quando a selecao/genero muda
  var buscaAtual = 0;

  vm.carregandoSequencias = true;
  vm.erroSequencias = "";
  vm.novaSequenciaTexto = "";
  vm.previewCadastro = [];
  vm.cadastrando = false;
  vm.erroCadastro = "";
  vm.mensagemCadastro = "";

  var parseResposta = function(data) {
    if (angular.isString(data)) {
      try {
        return angular.fromJson(data);
      } catch (erro) {
        return null;
      }
    }
    return data;
  };

  var paraSequencia = function(sequencia) {
    return {
      id: sequencia.id,
      acordes: (sequencia.acordes || []).map(function(acorde) {
        return { acorde: acorde, cor: COR_ACORDE };
      })
    };
  };

  vm.carregarSequencias = function() {
    vm.carregandoSequencias = true;
    vm.erroSequencias = "";

    $http.get("sequencias")
      .success(function(data) {
        var lista = parseResposta(data) || [];
        vm.sequenciasFamosas = lista.map(paraSequencia);
        vm.carregandoSequencias = false;
      })
      .error(function() {
        vm.erroSequencias = "Não foi possível carregar as sequências.";
        vm.carregandoSequencias = false;
      });
  };

  var separarAcordes = function(texto) {
    return (texto || "").split(",").map(function(acorde) {
      return acorde.trim();
    }).filter(function(acorde) {
      return acorde.length > 0;
    });
  };

  vm.atualizarPreview = function() {
    vm.previewCadastro = separarAcordes(vm.novaSequenciaTexto).map(function(acorde) {
      return { acorde: acorde, cor: COR_ACORDE };
    });
  };

  var sequenciaDoCatalogo = function(sequencia) {
    for (var i = 0; i < vm.sequenciasFamosas.length; i++) {
      if (vm.sequenciasFamosas[i].id === sequencia.id) {
        return vm.sequenciasFamosas[i];
      }
    }
    vm.sequenciasFamosas.push(sequencia);
    vm.sequenciasFamosas.sort(function(a, b) {
      return a.id - b.id;
    });
    return sequencia;
  };

  vm.cadastrarSequencia = function() {
    if (vm.cadastrando) {
      return;
    }

    vm.erroCadastro = "";
    vm.mensagemCadastro = "";
    vm.cadastrando = true;

    var acordes = separarAcordes(vm.novaSequenciaTexto);

    $http.post("sequencias", { acordes: acordes })
      .success(function(data) {
        var resposta = parseResposta(data);
        vm.cadastrando = false;

        if (!resposta || !resposta.id) {
          vm.erroCadastro = "Resposta inválida do servidor.";
          return;
        }

        var sequencia = sequenciaDoCatalogo(paraSequencia(resposta));
        if (resposta.duplicada) {
          vm.mensagemCadastro = "Essa sequência já existia; selecionando a original.";
        } else {
          vm.mensagemCadastro = "Sequência cadastrada.";
        }

        vm.novaSequenciaTexto = "";
        vm.previewCadastro = [];
        vm.pesquisarPorSequencia(sequencia);
      })
      .error(function(data) {
        var resposta = parseResposta(data);
        vm.cadastrando = false;
        vm.erroCadastro = (resposta && resposta.erro) ?
          resposta.erro : "Não foi possível cadastrar a sequência.";
      });
  };

  vm.temAcorde = function(acorde) {
    if (vm.minhaSequencia.acordes) {
      return (vm.minhaSequencia.acordes.indexOf(acorde) > -1);
    } else {
      return false;
    }
  };

  var createChordsString = function(chords) {
    var str = "";
    for (var i = 0; i < chords.length; i++) {
      str = str.concat(chords[i].acorde, ',');
    }
    return str.substring(0, str.length - 1);
  };

  var montarParams = function() {
    var params = { sequencia: createChordsString(vm.minhaSequencia.acordes) };
    if (vm.meuGenero !== "" && vm.meuGenero !== null) {
      params.generos = vm.meuGenero;
    }
    return params;
  };

  vm.pesquisarPorSequencia = function(sequencia) {
    if (sequencia) {
      vm.minhaSequencia = sequencia;
    }

    buscaAtual++;
    var token = buscaAtual;

    vm.pagina = 1;
    vm.temMais = false;
    vm.carregandoMais = false;
    vm.erroMais = "";
    vm.musics = [];

    if (!vm.minhaSequencia.acordes || !vm.minhaSequencia.acordes.length) {
      vm.esfigeSpeech = "";
      vm.isSearching = false;
      vm.showSearchResultsCount = false;
      return;
    }

    vm.progressbar.start();
    vm.esfigeSpeech = "Procurando músicas com base na sequencia...";
    vm.isSearching = true;
    vm.showSearchResultsCount = false;

    var params = montarParams();
    params.pagina = 1;

    $http.get("similares", { params: params })
      .success(function(data) {
        if (token !== buscaAtual) {
          return;
        }

        var resultado = parseResposta(data) || [];
        vm.progressbar.complete();
        vm.esfigeSpeech = "Encontrei essas músicas";
        vm.isSearching = false;
        vm.showSearchResultsCount = resultado.length > 0;
        vm.musics = resultado;
        vm.temMais = resultado.length === TAM_PAGINA;
      })
      .error(function() {
        if (token !== buscaAtual) {
          return;
        }

        vm.progressbar.complete();
        vm.esfigeSpeech = "Ops! Algo errado.";
        vm.isSearching = false;
        vm.showSearchResultsCount = false;
      });
  };

  vm.carregarMais = function() {
    if (vm.carregandoMais || !vm.temMais || vm.isSearching) {
      return;
    }

    var token = buscaAtual;
    vm.carregandoMais = true;
    vm.erroMais = "";

    var params = montarParams();
    params.pagina = vm.pagina + 1;

    $http.get("similares", { params: params })
      .success(function(data) {
        if (token !== buscaAtual) {
          return;
        }

        var resultado = parseResposta(data) || [];
        vm.carregandoMais = false;
        vm.pagina++;
        vm.musics = vm.musics.concat(resultado);
        vm.temMais = resultado.length === TAM_PAGINA;
      })
      .error(function() {
        if (token !== buscaAtual) {
          return;
        }

        vm.carregandoMais = false;
        vm.erroMais = "Não foi possível carregar mais resultados.";
      });
  };

  vm.limparPesquisa = function() {
    buscaAtual++;
    vm.minhaSequencia = {};
    vm.musics = [];
    vm.pagina = 1;
    vm.temMais = false;
    vm.carregandoMais = false;
    vm.erroMais = "";
    vm.showSearchResultsCount = false;
    vm.esfigeSpeech = "";
  };

  vm.goToLirics = function(music) {
    $window.open(music.url);
  };

  vm.goToResults = function() {
    vm.showSearchResultsCount = false;
    $("body").animate({ scrollTop: $("#results").offset().top }, "slow");
  };

  vm.carregarSequencias();
});
