/* ==========================================================
   MOONRISE  -  script.js
   1) Carrossel de destaques da página inicial
   2) Busca e menu do topo: fecha um quando o outro abre
   ========================================================== */

// ---------- 1) carrossel ----------
function iniciarCarrossel(vitrine) {
  var trilho = vitrine.querySelector(".slides");
  var pontos = vitrine.querySelectorAll(".ponto");
  var atual = 0;
  var poucoMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (pontos.length < 2) return;   // se tiver só 1 destaque não precisa de carrossel

  // vai pro slide número "n" (depois do último volta pro primeiro)
  function irPara(n) {
    atual = (n + pontos.length) % pontos.length;
    trilho.scrollTo({ left: trilho.clientWidth * atual, behavior: poucoMovimento ? "auto" : "smooth" });
  }

  // setas: data-ir="-1" volta 1, data-ir="1" avança 1
  vitrine.querySelectorAll(".seta").forEach(function (seta) {
    seta.addEventListener("click", function () {
      irPara(atual + Number(seta.dataset.ir));
    });
  });

  // bolinhas: cada uma leva pro seu slide
  pontos.forEach(function (ponto, i) {
    ponto.addEventListener("click", function () { irPara(i); });
  });

  // quando o slide muda (inclusive arrastando com o dedo) acende a bolinha certa
  trilho.addEventListener("scroll", function () {
    atual = Math.round(trilho.scrollLeft / trilho.clientWidth);
    pontos.forEach(function (ponto, i) {
      ponto.classList.toggle("ativo", i === atual);
    });
  });

  // passa sozinho a cada 7 segundos
  if (!poucoMovimento) {
    setInterval(function () { irPara(atual + 1); }, 7000);
  }
}

var vitrine = document.querySelector(".vitrine");
if (vitrine) iniciarCarrossel(vitrine);


// ---------- 2) busca e menu do topo ----------
var gavetas = document.querySelectorAll("details.gaveta");

gavetas.forEach(function (gaveta) {
  gaveta.addEventListener("toggle", function () {
    if (!gaveta.open) return;
    // fecha as outras gavetas
    gavetas.forEach(function (outra) {
      if (outra !== gaveta) outra.open = false;
    });
    // na busca já deixa o cursor no campo
    var campo = gaveta.querySelector("input");
    if (campo) campo.focus();
  });
});

// clicou fora, fecha tudo
document.addEventListener("click", function (evento) {
  gavetas.forEach(function (gaveta) {
    if (!gaveta.contains(evento.target)) gaveta.open = false;
  });
});
