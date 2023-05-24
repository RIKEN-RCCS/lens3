import { d as defineComponent, c as createBlock, w as withCtx, f as VContainer, o as openBlock, a as createVNode, g as VRow, h as createBaseVNode, i as createTextVNode, j as VResponsive, r as resolveComponent } from "./index.js";
const _hoisted_1 = /* @__PURE__ */ createBaseVNode("div", { class: "text-body-2 font-weight-light mb-n1" }, "Welcome to", -1);
const _hoisted_2 = /* @__PURE__ */ createBaseVNode("h1", { class: "text-h2 font-weight-bold" }, "Lenticularis S3", -1);
const _hoisted_3 = /* @__PURE__ */ createBaseVNode("div", { class: "py-14" }, null, -1);
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "About",
  setup(__props) {
    return (_ctx, _cache) => {
      const _component_router_link = resolveComponent("router-link");
      return openBlock(), createBlock(VContainer, { class: "fill-height" }, {
        default: withCtx(() => [
          createVNode(VResponsive, { class: "d-flex align-center text-center fill-height" }, {
            default: withCtx(() => [
              _hoisted_1,
              _hoisted_2,
              _hoisted_3,
              createVNode(VRow, { class: "d-flex align-center justify-center" }, {
                default: withCtx(() => [
                  createBaseVNode("p", null, [
                    createVNode(_component_router_link, { to: "/" }, {
                      default: withCtx(() => [
                        createTextVNode("Go to Home")
                      ]),
                      _: 1
                    })
                  ]),
                  createBaseVNode("p", null, [
                    createVNode(_component_router_link, { to: "/setting" }, {
                      default: withCtx(() => [
                        createTextVNode("Go to Setting")
                      ]),
                      _: 1
                    })
                  ]),
                  createBaseVNode("p", null, [
                    createVNode(_component_router_link, { to: "/about" }, {
                      default: withCtx(() => [
                        createTextVNode("Go to About")
                      ]),
                      _: 1
                    })
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      });
    };
  }
});
export {
  _sfc_main as default
};
