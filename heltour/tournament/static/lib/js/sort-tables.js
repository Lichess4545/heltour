const getCellValue = (tr, idx) =>
  tr.children[idx].innerText || tr.children[idx].textContent

const comparer = (idx, asc) => (a, b) =>
  ((v2, v1) =>
    v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2)
      ? v1 - v2
      : v1.toString().localeCompare(v2))(
    getCellValue(asc ? a : b, idx),
    getCellValue(asc ? b : a, idx)
  )

document.querySelectorAll('th.sort').forEach(th =>
  th.addEventListener('click', () => {
    const table = th.closest('table.sortable')
    const tbody = table.querySelector('tbody')
    Array.from(tbody.querySelectorAll('tr'))
      .sort(
        comparer(
          Array.from(th.parentNode.children).indexOf(th),
          (this.asc = !this.asc)
        )
      )
      .forEach(tr => tbody.appendChild(tr))
    $('.asc').removeClass('asc')
    $('.desc').removeClass('desc')
    th.classList.toggle('asc', !this.asc)
    th.classList.toggle('desc', this.asc)
  })
)
