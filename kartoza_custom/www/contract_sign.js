(function() {
  function setupCanvas(canvas) {
    const parent = canvas.parentElement;
    function resize() {
      const rect = parent.getBoundingClientRect();
      canvas.width = Math.floor(rect.width);
      canvas.height = Math.floor(rect.height);
      placeholder.style.display = 'block';
    }
    const placeholder = parent.querySelector('#sig-placeholder');
    resize();
    window.addEventListener('resize', resize);

    const ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#222';
    ctx.lineWidth = 2;
    let drawing = false;
    let last = null;

    function posFromEvent(e) {
      if (e.touches && e.touches[0]) {
        const rect = canvas.getBoundingClientRect();
        return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
      } else {
        const rect = canvas.getBoundingClientRect();
        return { x: e.clientX - rect.left, y: e.clientY - rect.top };
      }
    }

    function start(e) {
      drawing = true;
      last = posFromEvent(e);
      placeholder.style.display = 'none';
    }
    function move(e) {
      if (!drawing) return;
      const p = posFromEvent(e);
      ctx.beginPath();
      ctx.moveTo(last.x, last.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      last = p;
      e.preventDefault();
    }
    function end() { drawing = false; last = null; }

    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', move);
    window.addEventListener('mouseup', end);

    canvas.addEventListener('touchstart', start, {passive:false});
    canvas.addEventListener('touchmove', move, {passive:false});
    window.addEventListener('touchend', end);

    return {
      clear: function() { ctx.clearRect(0,0,canvas.width,canvas.height); placeholder.style.display='block'; },
      dataURL: function() { return canvas.toDataURL('image/png'); }
    };
  }

  function $(sel) { return document.querySelector(sel); }

  document.addEventListener('DOMContentLoaded', function() {
    const dataEl = document.getElementById('contract-data');
    const name = dataEl ? (dataEl.getAttribute('data-name') || '') : '';
    const canvas = document.getElementById('sig-canvas');
    const pad = setupCanvas(canvas);
    const clearBtn = document.getElementById('clear-btn');
    const signBtn = document.getElementById('sign-btn');
    const statusEl = document.getElementById('sign-status');
    const signeeInput = document.getElementById('signee');
    const agree = document.getElementById('agree');

    clearBtn.addEventListener('click', function() { pad.clear(); });

    signBtn.addEventListener('click', function() {
      statusEl.textContent = '';
      if (!name) { statusEl.textContent = 'Missing contract name.'; return; }
      if (!agree.checked) { statusEl.textContent = 'Please agree to the terms.'; return; }
      const signee = (signeeInput.value || '').trim();
      if (!signee) { statusEl.textContent = 'Please enter your full name.'; return; }
      const signature = pad.dataURL();
      if (!signature || signature.indexOf('data:image/png;base64,') !== 0) {
        statusEl.textContent = 'Please provide a signature.'; return;
      }
      signBtn.disabled = true;
      statusEl.textContent = 'Submitting…';

      frappe.call({
        method: 'kartoza_custom.www.contract_sign.sign_contract',
        args: { name: name, signee: signee, signature: signature },
      }).then(r => {
        const msg = (r && r.message) || {};
        if (msg.status === 'ok' || msg.status === 'already_signed') {
          const link = msg.attachment_url ? ` <a href="${msg.attachment_url}" target="_blank">Download PDF</a>` : '';
          statusEl.innerHTML = (msg.status === 'already_signed' ? 'Already signed.' : 'Signed successfully.') + link;
          signBtn.disabled = true;
        } else {
          statusEl.textContent = 'Unexpected response.';
          signBtn.disabled = false;
        }
      }).catch(err => {
        statusEl.textContent = (err && err.message) || 'Failed to sign.';
        signBtn.disabled = false;
      });
    });
  });
})();
