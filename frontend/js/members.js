function initSidebarNav() {
  const items = document.querySelectorAll(".sidebar-nav-item");
  if (!items.length) return;
  const sectionMap = {
    members: "section-hero",
    executives: "section-executives",
    associates: "section-associates",
    offices: "section-offices"
  };
  items.forEach(item => {
    item.addEventListener("click", e => {
      e.preventDefault();
      const section = item.dataset.section;
      const targetId = sectionMap[section];
      if (targetId) {
        document.getElementById(targetId).scrollIntoView({ behavior: "smooth" });
      }
    });
  });
}

function initIntersectionObserver() {
  const sections = document.querySelectorAll(".snap-section");
  const navItems = document.querySelectorAll(".sidebar-nav-item");
  if (!sections.length) return;
  const sectionKeyMap = {
    "section-hero": "members",
    "section-executives": "executives",
    "section-associates": "associates",
    "section-offices": "offices"
  };
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        sections.forEach(sec => {
          if (sec.id === id) {
            sec.classList.add("active-section");
          } else {
            sec.classList.remove("active-section");
          }
        });
        const activeKey = sectionKeyMap[id];
        navItems.forEach(item => {
          const section = item.dataset.section;
          const icon = item.querySelector(".sidebar-nav-icon");
          if (section === "offices") {
            if (section === activeKey) {
              item.classList.add("active");
              if (icon) icon.src = "../assets/members/badges/offices-icon-active-badge.webp";
            } else {
              item.classList.remove("active");
              if (icon) icon.src = "../assets/members/badges/offices-icon-inactive-badge.webp";
            }
          } else {
            const label = section === "associates" ? "Associate" : section.charAt(0).toUpperCase() + section.slice(1);
            if (section === activeKey) {
              item.classList.add("active");
              if (icon) icon.src = `../assets/members/badges/${label}-Active-State-Badge.webp`;
            } else {
              item.classList.remove("active");
              if (icon) icon.src = `../assets/members/badges/${label}-Inactive-State-Badge.webp`;
            }
          }
        });
      }
    });
  }, {
    root: null,
    rootMargin: "-50% 0px -50% 0px",
    threshold: 0
  });
  sections.forEach(sec => observer.observe(sec));
}

function initFooterObserver() {
  const footer = document.getElementById("footer-placeholder");
  const sidebar = document.querySelector(".members-sidebar");
  if (!footer || !sidebar) return;
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        sidebar.classList.add("at-footer");
      } else {
        sidebar.classList.remove("at-footer");
      }
    });
  }, {
    root: null,
    threshold: 0,
    rootMargin: "0px 0px -35px 0px"
  });
  observer.observe(footer);
}

function createCard(member) {
  const card = document.createElement("div");
  card.className = "member-card";
  
  const photoWrapper = document.createElement("div");
  photoWrapper.className = "member-photo-wrapper";
  
  const photoInner = document.createElement("div");
  photoInner.className = "member-photo-inner";
  
  const img = document.createElement("img");
  img.src = member.photo || "../assets/shared/components/AWS-NewLogo.webp";
  img.alt = "";
  img.className = "member-photo";
  
  photoInner.appendChild(img);
  photoWrapper.appendChild(photoInner);
  card.appendChild(photoWrapper);
  
  const name = document.createElement("p");
  name.className = "member-name";
  name.textContent = member.name;
  card.appendChild(name);
  
  if (member.role) {
    const role = document.createElement("p");
    role.className = "member-role";
    role.textContent = member.role;
    card.appendChild(role);
  }
  
  const position = document.createElement("p");
  position.className = "member-position";
  position.textContent = member.position;
  card.appendChild(position);
  
  const socials = document.createElement("div");
  socials.className = "member-socials";
  
  const socialIcons = {
    linkedin: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
    facebook: "M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z",
    instagram: "M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"
  };
  
  Object.entries(socialIcons).forEach(([platform, pathData]) => {
    if (member.socials && member.socials[platform]) {
      const link = document.createElement("a");
      link.href = member.socials[platform];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="black"><path d="${pathData}"/></svg>`;
      socials.appendChild(link);
    }
  });
  card.appendChild(socials);
  
  const links = document.createElement("div");
  links.className = "member-links";
  
  const linkIcons = {
    resume: "M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z",
    portfolio: "M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-2 .89-2 2v11c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z"
  };
  
  Object.entries(linkIcons).forEach(([type, pathData]) => {
    if (member[type]) {
      const link = document.createElement("a");
      link.href = member[type];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="black"><path d="${pathData}"/></svg>`;
      links.appendChild(link);
    }
  });
  card.appendChild(links);
  
  return card;
}

async function initMembers() {
  try {
    const response = await fetch("../data/members.json");
    const data = await response.json();
    
    ["executives", "associates", "offices"].forEach(sectionKey => {
      const members = data[sectionKey];
      const sectionEl = document.getElementById(`section-${sectionKey}`);
      if (!sectionEl) return;
      
      const container = sectionEl.querySelector(".founders-subsections");
      if (!container) return;
      
      if (!members || !members.length) {
        sectionEl.classList.add("hidden");
        return;
      }
      sectionEl.classList.remove("hidden");
      container.innerHTML = "";
      
      // Group members by subsection
      const grouped = {};
      members.forEach(member => {
        const subId = member.subsection || 1;
        if (!grouped[subId]) grouped[subId] = [];
        grouped[subId].push(member);
      });
      
      const subIds = Object.keys(grouped).sort((a, b) => a - b);
      
      const labels = {
        executives: [
          "EXECUTIVES",
          "The Executive Board drives the vision and operations of the AWS Student Builder Group, ensuring every initiative aligns with our mission to empower students through cloud technology and innovation."
        ],
        associates: {
          1: ["ASSOCIATES", ""],
          2: ["UI/UX", ""],
          3: ["FRONTEND", ""],
          4: ["BACKEND", ""]
        },
        offices: ["OFFICES", ""]
      };
      
      const isDesktop = window.matchMedia("(min-width: 1024px)").matches;
      
      if (Array.isArray(labels[sectionKey])) {
        if (isDesktop && sectionKey !== "founders" && sectionKey !== "executives" && sectionKey !== "offices") {
          // DESKTOP: Render a single unified grid
          const subsectionDiv = document.createElement("div");
          subsectionDiv.className = "founders-subsection";
          
          const headerDiv = document.createElement("div");
          headerDiv.className = "founders-header";
          
          const lineLeft = document.createElement("div");
          lineLeft.className = "founders-line";
          
          const title = document.createElement("h2");
          title.className = "founders-title";
          title.textContent = labels[sectionKey][0];
          
          const lineRight = document.createElement("div");
          lineRight.className = "founders-line";
          
          headerDiv.appendChild(lineLeft);
          headerDiv.appendChild(title);
          headerDiv.appendChild(lineRight);
          subsectionDiv.appendChild(headerDiv);
          
          const desc = document.createElement("p");
          desc.className = "founders-description";
          desc.textContent = labels[sectionKey][1];
          subsectionDiv.appendChild(desc);
          
          const gridDiv = document.createElement("div");
          gridDiv.className = "founders-grid";
          
          let index = 0;
          subIds.forEach(subId => {
            grouped[subId].forEach(member => {
              const card = createCard(member);
              card.setAttribute("data-index", index);
              gridDiv.appendChild(card);
              index++;
            });
          });
          
          subsectionDiv.appendChild(gridDiv);
          container.appendChild(subsectionDiv);
        } else {
          // MOBILE: Render original structure (separate subgroups with repeated headers)
          subIds.forEach(subId => {
            const subMembers = grouped[subId];
            const subsectionDiv = document.createElement("div");
            subsectionDiv.className = "founders-subsection";
            
            const headerDiv = document.createElement("div");
            headerDiv.className = "founders-header";
            
            const lineLeft = document.createElement("div");
            lineLeft.className = "founders-line";
            
            const title = document.createElement("h2");
            title.className = "founders-title";
            title.textContent = labels[sectionKey][0];
            
            const lineRight = document.createElement("div");
            lineRight.className = "founders-line";
            
            headerDiv.appendChild(lineLeft);
            headerDiv.appendChild(title);
            headerDiv.appendChild(lineRight);
            subsectionDiv.appendChild(headerDiv);
            
            const desc = document.createElement("p");
            desc.className = "founders-description";
            desc.textContent = labels[sectionKey][1];
            subsectionDiv.appendChild(desc);
            
            const gridDiv = document.createElement("div");
            gridDiv.className = "founders-grid";
            
            subMembers.forEach(member => {
              const card = createCard(member);
              gridDiv.appendChild(card);
            });
            
            subsectionDiv.appendChild(gridDiv);
            container.appendChild(subsectionDiv);
          });
        }
      } else {
        // Multi-subsection rendering (Associates)
        subIds.forEach(subId => {
          const subMembers = grouped[subId];
          const subsectionDiv = document.createElement("div");
          subsectionDiv.className = "founders-subsection";
          
          const headerDiv = document.createElement("div");
          headerDiv.className = "founders-header";
          
          const lineLeft = document.createElement("div");
          lineLeft.className = "founders-line";
          
          const title = document.createElement("h2");
          title.className = "founders-title";
          title.textContent = labels[sectionKey][subId][0];
          
          const lineRight = document.createElement("div");
          lineRight.className = "founders-line";
          
          headerDiv.appendChild(lineLeft);
          headerDiv.appendChild(title);
          headerDiv.appendChild(lineRight);
          subsectionDiv.appendChild(headerDiv);
          
          const desc = document.createElement("p");
          desc.className = "founders-description";
          desc.textContent = labels[sectionKey][subId][1];
          subsectionDiv.appendChild(desc);
          
          const gridDiv = document.createElement("div");
          gridDiv.className = "founders-grid";
          
          subMembers.forEach(member => {
            const card = createCard(member);
            gridDiv.appendChild(card);
          });
          
          subsectionDiv.appendChild(gridDiv);
          container.appendChild(subsectionDiv);
        });
      }
    });
  } catch (err) {
    console.error("Failed to load members data:", err);
  }
}

let resizeTimeout;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    initMembers();
  }, 250);
});

document.addEventListener("DOMContentLoaded", () => {
  initSidebarNav();
  initIntersectionObserver();
  initFooterObserver();
  initMembers();
});
