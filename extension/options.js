const portInput = document.getElementById("port");
const saveBtn = document.getElementById("save");
const status = document.getElementById("status");

chrome.storage.local.get({ port: 7323 }, (result) => {
  portInput.value = result.port;
});

saveBtn.addEventListener("click", () => {
  const port = parseInt(portInput.value, 10);
  if (Number.isNaN(port) || port < 1024 || port > 65535) {
    alert("Please enter a valid port number (1024-65535).");
    return;
  }

  chrome.storage.local.set({ port }, () => {
    status.style.display = "block";
    setTimeout(() => {
      status.style.display = "none";
    }, 2000);
  });
});
