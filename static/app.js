const books = [
  { title: "打造第二大脑", author: "Tiago Forte", cover: "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 0, time: "还未阅读", action: "创建", id: "book:3300045871" },
  { title: "JavaScript高级程序设计（第4版）", author: "Matt Frisbie", cover: "https://images.unsplash.com/photo-1532012197267-da84d127e765?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 87, time: "1时3分", action: "更新", id: "book:3300069921" },
  { title: "安徒生童话故事集", author: "安徒生", cover: "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=500&q=80", state: "想读", progress: 0, time: "还未阅读", action: "创建", id: "book:3300084217" },
  { title: "我还能看到多少次满月升起", author: "村上春树", cover: "https://images.unsplash.com/photo-1543002588-bfa74002ed7e?auto=format&fit=crop&w=500&q=80", state: "想读", progress: 0, time: "还未阅读", action: "创建", id: "book:3300017630" },
  { title: "当下的力量（白金版）", author: "埃克哈特·托利", cover: "https://images.unsplash.com/photo-1519682337058-a94d519337bc?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 8, time: "1时5分", action: "更新", id: "book:3300019912" },
  { title: "Android 开发者", author: "Google", cover: "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?auto=format&fit=crop&w=500&q=80", state: "想读", progress: 0, time: "还未阅读", action: "创建", id: "book:3300020112" },
  { title: "檀迦往事", author: "马伯庸", cover: "https://images.unsplash.com/photo-1495640388908-05fa85288e61?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 0, time: "2时34分", action: "更新", id: "book:3300028471" },
  { title: "打造第二大脑", author: "Tiago Forte", cover: "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 32, time: "2时20分", action: "无变化", id: "book:3300045871-copy" },
  { title: "我们为什么要睡觉？", author: "马修·沃克", cover: "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 2, time: "9分", action: "创建", id: "book:3300038712" },
  { title: "霍乱时期的爱情", author: "加西亚·马尔克斯", cover: "https://images.unsplash.com/photo-1543002588-bfa74002ed7e?auto=format&fit=crop&w=500&q=80", state: "finished", progress: 100, time: "13时7分", action: "无变化", id: "book:3300042831" },
  { title: "非暴力沟通（修订版）", author: "马歇尔·卢森堡", cover: "https://images.unsplash.com/photo-1511108690759-009324a90311?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 0, time: "4分", action: "创建", id: "book:3300077612" },
  { title: "强风吹拂（2023版）", author: "三浦紫苑", cover: "https://images.unsplash.com/photo-1535398089889-dd807df1ee32?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 6, time: "11分", action: "更新", id: "book:3300091121" },
  { title: "笔记的方法", author: "大岛武史", cover: "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 0, time: "5分", action: "创建", id: "book:3300071110" },
  { title: "纳瓦尔宝典", author: "埃里克·乔根森", cover: "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 91, time: "7时52分", action: "更新", id: "book:3300069912" },
  { title: "狼（世界文学名著经典）", author: "杰克·伦敦", cover: "https://images.unsplash.com/photo-1543002588-bfa74002ed7e?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 0, time: "1分", action: "创建", id: "book:3300031088" },
  { title: "生命之书：365天的静心冥想", author: "克里希那穆提", cover: "https://images.unsplash.com/photo-1519682337058-a94d519337bc?auto=format&fit=crop&w=500&q=80", state: "reading", progress: 6, time: "1时19分", action: "更新", id: "book:3300040007" },
];

const heatmap = document.querySelector("#heatmap");
const bookGrid = document.querySelector("#bookGrid");
const bookTotal = document.querySelector("#bookTotal");
const modeSelect = document.querySelector("#modeSelect");
const toast = document.querySelector("#toast");
let filter = "all";

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2800);
}

function renderHeatmap() {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  heatmap.innerHTML = `<div class="heatmap-months">${months.map((month) => `<span>${month}</span>`).join("")}</div><div class="heatmap-grid">${Array.from({length: 126}, (_, index) => `<i class="heat-${(index * 7 + 3) % 5}"></i>`).join("")}</div>`;
}

function stateLabel(state) {
  return state === "finished" ? "已读" : state === "reading" ? "在读" : "想读";
}

function renderBooks() {
  let visible = books;
  if (filter === "finished" || filter === "reading" || filter === "想读") visible = books.filter((book) => book.state === filter);
  if (filter === "sync") visible = books.filter((book) => book.action !== "无变化");
  if (modeSelect.value === "incremental") visible = visible.filter((book) => book.action !== "无变化");
  bookTotal.textContent = `${visible.length} 本`;
  bookGrid.innerHTML = visible.map((book) => `
    <article class="book-card">
      <div class="cover-wrap"><img src="${book.cover}" alt="${book.title}封面" loading="lazy"><span class="sync-action ${book.action === "更新" ? "update" : book.action === "无变化" ? "unchanged" : "create"}">${book.action}</span></div>
      <div class="book-info"><h3>${book.title}</h3><p class="book-author">${book.author}</p><span class="reading-state ${book.state}">${stateLabel(book.state)}</span><div class="progress-line"><i style="width:${Math.min(book.progress, 100)}%"></i></div><div class="book-footer"><span>${book.progress}%</span><em>${book.time}</em></div><code>${book.id}</code></div>
    </article>
  `).join("");
}

renderHeatmap();
renderBooks();

document.querySelectorAll(".book-tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".book-tab").forEach((item) => item.classList.remove("active"));
  tab.classList.add("active");
  filter = tab.dataset.filter;
  renderBooks();
}));

modeSelect.addEventListener("change", () => {
  renderBooks();
  showToast(modeSelect.value === "full" ? "已切换到首次全量预览" : "已切换到后续增量预览");
});

document.querySelectorAll(".side-link").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll(".side-link").forEach((item) => item.classList.remove("active"));
  link.classList.add("active");
  if (link.dataset.side === "sync") showToast("同步预览已准备，确认后接入本地配置");
  else if (link.dataset.side !== "books") showToast(`${link.textContent.trim()}视图将在真实数据接入后展开`);
}));

document.querySelector("#refreshButton").addEventListener("click", () => showToast("预览数据已刷新"));
document.querySelector("#searchButton").addEventListener("click", () => showToast("搜索将在真实数据接入后启用"));
document.querySelector("#approveButton").addEventListener("click", () => showToast("界面方案已确认，下一步接入 config/local.toml"));
