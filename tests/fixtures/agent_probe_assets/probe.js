window.addEventListener('DOMContentLoaded', async () => {
  const status = document.getElementById('status');
  try {
    const response = await fetch('./data.json');
    const data = await response.json();
    status.textContent = `asset ${data.name}`;
  } catch (error) {
    status.textContent = 'asset fetch failed';
  }
});
