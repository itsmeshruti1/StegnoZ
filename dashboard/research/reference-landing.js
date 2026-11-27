function setQuery(question) {
  const input = document.getElementById("research-query-input");
  input.value = question;
  input.focus();
}
function toggleMotion() {
  const stage = document.getElementById("threejs-container-ANIMATION_17");
  const dimmed = stage.style.opacity === "0.16";
  stage.style.opacity = dimmed ? "1" : "0.16";
  document.getElementById("motion-label").textContent = dimmed ? "Dim backdrop" : "Show backdrop";
  document.getElementById("motion-icon").textContent = dimmed ? "visibility_off" : "visibility";
  document.getElementById("motion-toggle-btn").setAttribute("aria-pressed", String(!dimmed));
}
document.getElementById("hero-explore-cta").addEventListener("click", (event) => {
  const question = document.getElementById("research-query-input").value.trim();
  if (question) event.currentTarget.href = "/dashboard?q=" + encodeURIComponent(question);
});
document.getElementById("research-query-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    document.getElementById("hero-explore-cta").click();
  }
});
if (window.gsap && window.ScrollTrigger && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
  gsap.registerPlugin(ScrollTrigger);
  gsap.utils.toArray(".gs-reveal").forEach((element) => {
    gsap.fromTo(element, { opacity: 0, y: 30 }, {
      opacity: 1, y: 0, duration: .85, ease: "power2.out",
      scrollTrigger: { trigger: element, start: "top 88%", once: true },
    });
  });
}
